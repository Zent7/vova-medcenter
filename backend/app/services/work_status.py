"""Статус «На работу / С работы»: отметки сотрудника и месячная сводка по дням.

План дня берется из графика (`staff_schedule_days`) и складывается по медцентрам, в которых сотрудник стоит в этот день; факт — из отметок. Отметка, которая
перешла через полночь, делится по местным дням. Переработка — факт сверх плана дня.

Допуск 15 минут у начала и конца смены: опоздание на работу и ранний уход считаются по плану (`rounded_marks`).
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.staff_schedule_day import StaffScheduleDay
from app.models.user import User
from app.models.work_time_entry import WorkTimeEntry
from app.services import work_schedule as schedule

FALLBACK_TIMEZONE = "Europe/Moscow"

# Допуск у начала и конца смены: отметка «На работу» в пределах этого времени после начала смены считается с начала,
# отметка «С работы» в пределах этого времени до конца смены — до конца.
SHIFT_EDGE_GRACE = timedelta(minutes=15)


def local_zone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.xml_exports_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo(FALLBACK_TIMEZONE)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(moment: datetime) -> datetime:
    """Момент в UTC. Время без пояса считаем UTC: так его отдает SQLite, а отметки и так хранятся в UTC."""
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc)


def local_today(now: datetime) -> date:
    return now.astimezone(local_zone()).date()


def open_entry(db: Session, user: User) -> WorkTimeEntry | None:
    return db.execute(
        select(WorkTimeEntry)
        .where(WorkTimeEntry.user_id == user.id, WorkTimeEntry.ended_at.is_(None))
        .order_by(WorkTimeEntry.started_at.desc())
    ).scalars().first()


def start_work(db: Session, user: User, now: datetime) -> WorkTimeEntry:
    """«На работу»: повторное нажатие не создает вторую отметку, а возвращает открытую."""
    entry = open_entry(db, user)
    if entry is None:
        entry = WorkTimeEntry(user_id=user.id, started_at=as_utc(now))
        db.add(entry)
        db.flush()
    return entry


def stop_work(db: Session, user: User, now: datetime) -> WorkTimeEntry | None:
    """«С работы»: закрывает открытую отметку; без открытой ничего не делает."""
    entry = open_entry(db, user)
    if entry is not None:
        entry.ended_at = as_utc(now)
        db.flush()
    return entry


def minutes_by_local_day(started_at: datetime, ended_at: datetime, first: date, last: date) -> dict[date, int]:
    """Минуты отметки по местным дням внутри периода от first до last включительно."""
    zone = local_zone()
    start_local = as_utc(started_at).astimezone(zone)
    end_local = as_utc(ended_at).astimezone(zone)
    result: dict[date, int] = {}
    day = max(start_local.date(), first)
    stop_day = min(end_local.date(), last)
    while day <= stop_day:
        day_start = datetime.combine(day, time.min, tzinfo=zone)
        day_end = day_start + timedelta(days=1)
        begin = max(start_local, day_start)
        finish = min(end_local, day_end)
        minutes = int((finish - begin).total_seconds() // 60)
        if minutes > 0:
            result[day] = result.get(day, 0) + minutes
        day += timedelta(days=1)
    return result


def plan_minutes(row: StaffScheduleDay | None) -> int:
    """План дня: длительность смены; отгул, больничный, отпуск и пустой день — ноль."""
    if row is None or row.kind != "shift" or row.start_time is None or row.end_time is None:
        return 0
    return schedule.shift_minutes(row.start_time, row.end_time)


def planned_shifts(rows: list[StaffScheduleDay]) -> list[tuple[datetime, datetime]]:
    """Плановые смены в UTC: (начало, конец). Ночная смена кончается в следующем местном дне."""
    zone = local_zone()
    shifts = []
    for row in rows:
        if row.kind != "shift" or row.start_time is None or row.end_time is None:
            continue
        begins = datetime.combine(row.work_date, row.start_time, tzinfo=zone)
        finish = begins + timedelta(minutes=schedule.shift_minutes(row.start_time, row.end_time))
        shifts.append((begins.astimezone(timezone.utc), finish.astimezone(timezone.utc)))
    return shifts


def rounded_marks(
    entries: list[WorkTimeEntry], now: datetime, shifts: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    """Отметки по времени с округлением к плану (допуск SHIFT_EDGE_GRACE, 15 минут).

    Опоздание: отметка «На работу» в пределах допуска после начала смены считается с начала смены.
    Ранний уход: отметка «С работы» в пределах допуска до конца смены считается до конца смены.
    Отметка, которая целиком укладывается в допуск, не округляется, иначе короткий заход раздувается.
    Округление не накладывает отметки друг на друга: соседняя отметка задает границу.
    Открытая отметка идет до now и до конца смены не округляется.
    """
    marks = sorted(entries, key=lambda entry: as_utc(entry.started_at))
    result: list[tuple[datetime, datetime]] = []
    for index, entry in enumerate(marks):
        raw_start = as_utc(entry.started_at)
        closed = entry.ended_at is not None
        raw_end = as_utc(entry.ended_at) if closed else now
        start, end = raw_start, raw_end

        late = [begins for begins, _ in shifts if begins < raw_start <= begins + SHIFT_EDGE_GRACE]
        if late and raw_end > max(late) + SHIFT_EDGE_GRACE:
            planned_start = max(late)
            if result:
                planned_start = max(planned_start, result[-1][1])
            start = min(raw_start, planned_start)

        early = [finish for _, finish in shifts if finish - SHIFT_EDGE_GRACE <= raw_end < finish]
        if closed and early and raw_start < min(early) - SHIFT_EDGE_GRACE:
            planned_end = min(early)
            if index + 1 < len(marks):
                planned_end = min(planned_end, as_utc(marks[index + 1].started_at))
            end = max(raw_end, planned_end)

        result.append((start, end))
    return result


def planned_shifts_by_user(
    db: Session, first: date, last: date, user_id: int | None = None
) -> dict[int, list[tuple[datetime, datetime]]]:
    """Плановые смены по сотрудникам. Берем и соседние дни: ночная смена последнего дня кончается в следующем."""
    query = select(StaffScheduleDay).where(
        StaffScheduleDay.kind == "shift",
        StaffScheduleDay.work_date.between(first - timedelta(days=1), last + timedelta(days=1)),
    )
    if user_id is not None:
        query = query.where(StaffScheduleDay.user_id == user_id)
    grouped: dict[int, list[StaffScheduleDay]] = defaultdict(list)
    for row in db.execute(query).scalars():
        grouped[row.user_id].append(row)
    return {owner_id: planned_shifts(rows) for owner_id, rows in grouped.items()}


def period_entries(db: Session, first: date, last: date, user_id: int | None = None) -> list[WorkTimeEntry]:
    """Отметки, которые пересекают период с first по last по местным дням. user_id — один сотрудник."""
    zone = local_zone()
    utc_start = datetime.combine(first, time.min, tzinfo=zone).astimezone(timezone.utc)
    utc_end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    query = select(WorkTimeEntry).where(
        WorkTimeEntry.started_at < utc_end,
        (WorkTimeEntry.ended_at.is_(None)) | (WorkTimeEntry.ended_at > utc_start),
    )
    if user_id is not None:
        query = query.where(WorkTimeEntry.user_id == user_id)
    return list(db.execute(query).scalars())


def fact_minutes_by_day(
    entries: list[WorkTimeEntry],
    first: date,
    last: date,
    now: datetime,
    shifts: list[tuple[datetime, datetime]] | None = None,
) -> dict[date, int]:
    """Факт по местным дням: минуты отметок после округления к плану (rounded_marks). Открытая отметка идет до now."""
    fact: dict[date, int] = {}
    for start, end in rounded_marks(entries, now, shifts or []):
        for day, minutes in minutes_by_local_day(start, end, first, last).items():
            fact[day] = fact.get(day, 0) + minutes
    return fact


def fact_minutes_by_user(db: Session, first: date, last: date, now: datetime) -> dict[int, dict[date, int]]:
    """Факт по дням у каждого сотрудника. Статистика админа берет его отсюда же, что и статус."""
    grouped: dict[int, list[WorkTimeEntry]] = defaultdict(list)
    for entry in period_entries(db, first, last):
        grouped[entry.user_id].append(entry)
    planned = planned_shifts_by_user(db, first, last)
    return {
        user_id: fact_minutes_by_day(entries, first, last, now, planned.get(user_id))
        for user_id, entries in grouped.items()
    }


def marks_list(entries: list[WorkTimeEntry], now: datetime) -> list[dict]:
    """Отметки для списка «Начало — Конец — Длительность», новые сверху. Открытая отметка идет до now."""
    marks = []
    for entry in entries:
        started = as_utc(entry.started_at)
        ended = as_utc(entry.ended_at) if entry.ended_at is not None else None
        finish = ended if ended is not None else now
        marks.append(
            {
                "started_at": started,
                "ended_at": ended,
                "duration_seconds": max(int((finish - started).total_seconds()), 0),
            }
        )
    return sorted(marks, key=lambda mark: mark["started_at"], reverse=True)


def marks_by_user(db: Session, first: date, last: date, now: datetime) -> dict[int, list[dict]]:
    """Отметки месяца у каждого сотрудника для статистики графика: тот же период, что у факта."""
    grouped: dict[int, list[WorkTimeEntry]] = defaultdict(list)
    for entry in period_entries(db, first, last):
        grouped[entry.user_id].append(entry)
    return {user_id: marks_list(entries, now) for user_id, entries in grouped.items()}


def day_kind(rows: list[StaffScheduleDay]) -> str | None:
    """Вид дня для сводки: смена, если в каком-то медцентре стоит смена; иначе вид первой записи."""
    if not rows:
        return None
    if any(row.kind == "shift" for row in rows):
        return "shift"
    return rows[0].kind


def month_payload(db: Session, user: User, year: int, month: int, now: datetime) -> dict:
    first, last = schedule.month_bounds(year, month)

    plan_rows = db.execute(
        select(StaffScheduleDay).where(
            StaffScheduleDay.user_id == user.id,
            StaffScheduleDay.work_date >= first,
            StaffScheduleDay.work_date <= last,
        )
    ).scalars().all()
    by_date: dict[date, list[StaffScheduleDay]] = defaultdict(list)
    for row in plan_rows:
        by_date[row.work_date].append(row)

    shifts = planned_shifts_by_user(db, first, last, user.id).get(user.id)
    entries = period_entries(db, first, last, user.id)
    fact_minutes = fact_minutes_by_day(entries, first, last, now, shifts)

    days = []
    total_plan = total_fact = total_over = 0
    for day in schedule.days_in_range(first, last):
        rows = by_date.get(day, [])
        plan = sum(plan_minutes(row) for row in rows)
        fact = fact_minutes.get(day, 0)
        over = max(fact - plan, 0)
        total_plan += plan
        total_fact += fact
        total_over += over
        days.append(
            {
                "work_date": day,
                "kind": day_kind(rows),
                "plan_hours": schedule.minutes_to_hours(plan),
                "fact_hours": schedule.minutes_to_hours(fact),
                "overtime_hours": schedule.minutes_to_hours(over),
            }
        )

    open_now = open_entry(db, user)
    open_payload = None
    if open_now is not None:
        started = as_utc(open_now.started_at)
        elapsed = int((now - started).total_seconds())
        open_payload = {"started_at": started, "elapsed_seconds": max(elapsed, 0)}

    return {
        "year": year,
        "month": month,
        "days_in_month": len(days),
        "today": local_today(now),
        "now": now,
        "open": open_payload,
        "days": days,
        "marks": marks_list(entries, now),
        "totals": {
            "plan_hours": schedule.minutes_to_hours(total_plan),
            "fact_hours": schedule.minutes_to_hours(total_fact),
            "overtime_hours": schedule.minutes_to_hours(total_over),
        },
    }
