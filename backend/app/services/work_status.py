"""Статус «На работу / С работы»: отметки сотрудника и месячная сводка по дням.

План дня берется из графика (`staff_schedule_days`), факт — из отметок. Отметка, которая
перешла через полночь, делится по местным дням. Переработка — факт сверх плана дня.
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


def fact_minutes_by_day(entries: list[WorkTimeEntry], first: date, last: date, now: datetime) -> dict[date, int]:
    """Факт по местным дням: минуты отметок. Открытая отметка идет до now."""
    fact: dict[date, int] = {}
    for entry in entries:
        ended = as_utc(entry.ended_at) if entry.ended_at is not None else now
        for day, minutes in minutes_by_local_day(entry.started_at, ended, first, last).items():
            fact[day] = fact.get(day, 0) + minutes
    return fact


def fact_minutes_by_user(db: Session, first: date, last: date, now: datetime) -> dict[int, dict[date, int]]:
    """Факт по дням у каждого сотрудника. Статистика админа берет его отсюда же, что и статус."""
    grouped: dict[int, list[WorkTimeEntry]] = defaultdict(list)
    for entry in period_entries(db, first, last):
        grouped[entry.user_id].append(entry)
    return {user_id: fact_minutes_by_day(entries, first, last, now) for user_id, entries in grouped.items()}


def month_payload(db: Session, user: User, year: int, month: int, now: datetime) -> dict:
    first, last = schedule.month_bounds(year, month)

    plan_rows = db.execute(
        select(StaffScheduleDay).where(
            StaffScheduleDay.user_id == user.id,
            StaffScheduleDay.work_date >= first,
            StaffScheduleDay.work_date <= last,
        )
    ).scalars().all()
    by_date = {row.work_date: row for row in plan_rows}

    fact_minutes = fact_minutes_by_day(period_entries(db, first, last, user.id), first, last, now)

    days = []
    total_plan = total_fact = total_over = 0
    for day in schedule.days_in_range(first, last):
        row = by_date.get(day)
        plan = plan_minutes(row)
        fact = fact_minutes.get(day, 0)
        over = max(fact - plan, 0)
        total_plan += plan
        total_fact += fact
        total_over += over
        days.append(
            {
                "work_date": day,
                "kind": row.kind if row is not None else None,
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
        "totals": {
            "plan_hours": schedule.minutes_to_hours(total_plan),
            "fact_hours": schedule.minutes_to_hours(total_fact),
            "overtime_hours": schedule.minutes_to_hours(total_over),
        },
    }
