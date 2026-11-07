"""График работы по медцентрам: смены по шаблону, отгулы, больничные, отпуска и фактические часы.

У каждого медцентра свой график сотрудника (`staff_center_schedules`): шаблон (`2/2`, `3/3`, `4/4`,
`5/2`, `6/1`), время смены и первая смена цикла. Дни (`staff_schedule_days`) записаны в том же медцентре.
Шаблон задает только порядок: первая смена ставится кнопкой «Назначить первую смену»; если график
сохранен без нее, она ставится на сегодня (`start_plan_if_missing`). Дальше дни считаются от первой
смены без пропусков. «Создать график» заполняет пустые дни месяца в том же порядке, поэтому
смена 31 числа и смена 1 числа идут подряд. Ручные записи (время, отгул, больничный, отпуск) шаблон
не сдвигают. Если сотрудник в один день стоит сменой в двух медцентрах, оба дня помечаются как пересечение.
"""

from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.models.center import Center
from app.models.staff_center_schedule import StaffCenterSchedule
from app.models.staff_schedule_day import StaffScheduleDay
from app.models.user import Role, User
from app.services.audit import write_audit_log

# Порядок в таблице: сначала операторы, потом врачи и председатель. Админ медцентра не имеет, в таблицу не попадает.
SCHEDULE_ROLE_ORDER = ("operator", "doctor", "chairman")
# Кто открывает график: админ видит и ставки, врач и оператор — только свои медцентры и без денег.
VIEWER_ROLE_CODES = ("admin", "operator", "doctor")
# Цвет медцентра. Известные коды закреплены за слотом, остальные берут цвет по номеру.
CENTER_PALETTE = ("#2F6FB3", "#2E9E6A", "#D9822B", "#8E5BB5", "#C0504D", "#3A9AA8")
CENTER_PALETTE_SLOTS = {"center-a": 0, "center-b": 1, "center-c": 2}
MINUTES_PER_DAY = 24 * 60
MAX_ABSENCE_DAYS = 366
TWO_PLACES = Decimal("0.01")
AUDIT_ENTITY = "staff_schedule"


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def local_today() -> date:
    """Сегодня по местному времени (Москва): план и отметки считаются по местным дням."""
    try:
        zone = ZoneInfo(settings.xml_exports_timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Europe/Moscow")
    return datetime.now(zone).date()


def days_in_range(first: date, last: date) -> list[date]:
    if last < first:
        return []
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def parse_pattern(pattern: str) -> tuple[int, int]:
    """`4/4` -> (4, 4): сколько дней подряд работают и сколько отдыхают."""
    work, rest = pattern.split("/")
    return int(work), int(rest)


def shift_minutes(start: time, end: time) -> int:
    """Минуты смены «со скольки — до скольки»; если конец раньше начала, смена ночная."""
    return (end.hour * 60 + end.minute - start.hour * 60 - start.minute) % MINUTES_PER_DAY


def minutes_to_hours(minutes: int) -> float:
    return float((Decimal(minutes) / Decimal(60)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


def pay_for(minutes: int, rate: Decimal | None) -> float | None:
    if rate is None:
        return None
    return float((Decimal(minutes) * rate / Decimal(60)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


def format_time(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value is not None else None


def center_color(center: Center) -> str:
    slot = CENTER_PALETTE_SLOTS.get(center.code, center.id)
    return CENTER_PALETTE[slot % len(CENTER_PALETTE)]


def center_payload(center: Center) -> dict:
    return {"id": center.id, "name": center.name, "color": center_color(center)}


def pattern_shifts(schedule: StaffCenterSchedule, first: date, last: date) -> list[tuple[date, int]]:
    """Смены по шаблону в промежутке: (день, номер смены). До первой смены цикла шаблон ничего не ставит."""
    if not schedule.schedule_pattern or schedule.schedule_anchor_date is None:
        return []
    work, rest = parse_pattern(schedule.schedule_pattern)
    anchor = schedule.schedule_anchor_date
    result = []
    for work_date in days_in_range(max(first, anchor), last):
        position = (work_date - anchor).days % (work + rest)
        if position < work:
            result.append((work_date, position + 1))
    return result


def _user_options():
    return (
        joinedload(User.role),
        joinedload(User.center),
        selectinload(User.extra_centers),
        selectinload(User.center_schedules),
    )


def load_schedule_user(db: Session, user_id: int) -> User:
    user = db.execute(select(User).options(*_user_options()).where(User.id == user_id)).unique().scalar_one_or_none()
    if user is None or user.role.code not in SCHEDULE_ROLE_ORDER:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден")
    return user


def works_in(user: User, center_id: int) -> bool:
    return center_id in {center.id for center in user.work_centers}


def load_schedule_center(db: Session, user: User, center_id: int) -> Center:
    """Медцентр, в котором сотрудник работает: только там его график открывается и правится."""
    center = db.get(Center, center_id)
    if center is None or not works_in(user, center_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не работает в этом медцентре")
    return center


def check_day_update(kind: str, start: time | None, end: time | None) -> None:
    if kind == "shift":
        if start is None or end is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите, со скольки и до скольки работает сотрудник")
        if start == end:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Начало и конец смены не должны совпадать")
    elif start is not None or end is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="У отгула, больничного и отпуска не бывает времени смены")


def check_absence_period(date_from: date, date_to: date) -> list[date]:
    if date_to < date_from:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Дата «по» не может быть раньше даты «с»")
    days = days_in_range(date_from, date_to)
    if len(days) > MAX_ABSENCE_DAYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Период не может быть длиннее года")
    return days


def active_centers(db: Session) -> list[Center]:
    return list(db.execute(select(Center).where(Center.is_active.is_(True)).order_by(Center.id)).scalars())


def scope_centers(db: Session, viewer: User) -> list[Center]:
    """Медцентры, которые видит смотрящий: админ — все активные, врач и оператор — свои, основной первым."""
    if viewer.role.code == "admin":
        return active_centers(db)
    return [center for center in viewer.work_centers if center.is_active]


def pick_center(db: Session, viewer: User, center_id: int | None) -> Center:
    """Медцентр таблицы: названный смотрящему доступен, без названия — первый из его медцентров."""
    scope = scope_centers(db, viewer)
    if center_id is None:
        if not scope:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Медцентр не назначен")
        return scope[0]
    for center in scope:
        if center.id == center_id:
            return center
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Этот медцентр вам недоступен")


def schedule_users(db: Session) -> list[User]:
    return list(
        db.execute(
            select(User)
            .options(*_user_options())
            .join(Role, User.role_id == Role.id)
            .where(Role.code.in_(SCHEDULE_ROLE_ORDER))
        ).unique().scalars()
    )


def _days_by_user(db: Session, first: date, last: date, center_id: int) -> dict[int, list[StaffScheduleDay]]:
    grouped: dict[int, list[StaffScheduleDay]] = defaultdict(list)
    rows = db.execute(
        select(StaffScheduleDay)
        .where(StaffScheduleDay.center_id == center_id, StaffScheduleDay.work_date.between(first, last))
        .order_by(StaffScheduleDay.work_date)
    ).scalars()
    for row in rows:
        grouped[row.user_id].append(row)
    return grouped


def _sort_key(user: User) -> tuple[int, str, int]:
    return (SCHEDULE_ROLE_ORDER.index(user.role.code), (user.full_name or user.login).lower(), user.id)


def visible_users(users: list[User], days_by_user: dict, center_id: int) -> list[User]:
    """Кто попадает в таблицу медцентра: все, кто в нем работает, даже без графика — строку нужно заполнить.

    Отключенный сотрудник остается, пока у него есть дни в этом месяце, — чтобы история не пропала из таблицы.
    """
    result = []
    for user in users:
        if not works_in(user, center_id):
            continue
        if not user.is_active and not days_by_user.get(user.id):
            continue
        result.append(user)
    return sorted(result, key=_sort_key)


def _other_center_shifts(
    db: Session,
    user_ids: list[int],
    first: date,
    last: date,
    center_id: int,
    scope_ids: list[int],
) -> dict[tuple[int, date], list[dict]]:
    """Смены тех же сотрудников в других медцентрах в те же дни. Только медцентры, которые видит смотрящий."""
    result: dict[tuple[int, date], list[dict]] = defaultdict(list)
    if not user_ids or not scope_ids:
        return result
    rows = db.execute(
        select(StaffScheduleDay, Center.name)
        .join(Center, Center.id == StaffScheduleDay.center_id)
        .where(
            StaffScheduleDay.user_id.in_(user_ids),
            StaffScheduleDay.work_date.between(first, last),
            StaffScheduleDay.kind == "shift",
            StaffScheduleDay.center_id != center_id,
            StaffScheduleDay.center_id.in_(scope_ids),
        )
        .order_by(Center.id)
    ).all()
    for row, center_name in rows:
        result[(row.user_id, row.work_date)].append(
            {
                "center_id": row.center_id,
                "center_name": center_name,
                "start_time": format_time(row.start_time),
                "end_time": format_time(row.end_time),
            }
        )
    return result


def _day_payload(row: StaffScheduleDay, conflicts: list[dict]) -> dict:
    is_shift = row.kind == "shift"
    return {
        "work_date": row.work_date,
        "kind": row.kind,
        "start_time": format_time(row.start_time),
        "end_time": format_time(row.end_time),
        "fact_start_time": format_time(row.fact_start_time),
        "fact_end_time": format_time(row.fact_end_time),
        "source": row.source,
        "shift_no": row.shift_no if is_shift else None,
        # Смены того же сотрудника в других медцентрах в этот день: по ним клетка красная.
        "conflicts": conflicts if is_shift else [],
    }


def month_payload(db: Session, viewer: User, center: Center, year: int, month: int) -> dict:
    """Таблица месяца одного медцентра. Ставки сюда не попадают — их отдает только статистика."""
    first, last = month_bounds(year, month)
    days_by_user = _days_by_user(db, first, last, center.id)
    scope_ids = [item.id for item in scope_centers(db, viewer)]
    users = visible_users(schedule_users(db), days_by_user, center.id)
    conflicts = _other_center_shifts(db, [user.id for user in users], first, last, center.id, scope_ids)

    rows = []
    for user in users:
        schedule = user.schedule_in(center.id)
        rows.append(
            {
                "user_id": user.id,
                "full_name": user.full_name or user.login,
                "role_code": user.role.code,
                "role_name": user.role.name,
                "is_active": user.is_active,
                "pattern": schedule.schedule_pattern if schedule else None,
                "shift_start": format_time(schedule.schedule_start) if schedule else None,
                "shift_end": format_time(schedule.schedule_end) if schedule else None,
                "days": [
                    _day_payload(row, conflicts.get((user.id, row.work_date), []))
                    for row in days_by_user.get(user.id, [])
                ],
            }
        )
    return {
        "year": year,
        "month": month,
        "days_in_month": last.day,
        "can_edit": viewer.role.code == "admin",
        "center": center_payload(center),
        "centers": [center_payload(item) for item in scope_centers(db, viewer)],
        "rows": rows,
    }


def stats_payload(
    db: Session,
    center: Center,
    year: int,
    month: int,
    counted_minutes: dict[int, dict[date, int]],
    *,
    only_user_id: int | None = None,
    with_money: bool = True,
    marks: dict[int, list[dict]] | None = None,
) -> dict:
    """План и факт по сотрудникам медцентра за месяц; с деньгами — сумма «часы × ставка».

    Админ получает всех со ставками и суммами. Врач и оператор получают `only_user_id` и
    `with_money=False`: одна строка без ставки и сумм, часы остаются.

    Факт дня — ручная правка на смене этого медцентра, если она задана; иначе минуты отметок «На работу»
    за местный день (`counted_minutes` от work_status.fact_minutes_by_user). Отметки дня считаются один
    раз: в медцентре, где у сотрудника смена в этот день (см. _mark_owners). Без отметок факт нулевой.
    `marks` — отметки каждого сотрудника за месяц (work_status.marks_by_user) для списка в статистике.
    """
    first, last = month_bounds(year, month)
    days_by_user = _days_by_user(db, first, last, center.id)
    users = visible_users(schedule_users(db), days_by_user, center.id)
    owners = _mark_owners(db, users, first, last)
    if only_user_id is not None:
        users = [user for user in users if user.id == only_user_id]

    rows = []
    for user in users:
        schedule = user.schedule_in(center.id)
        by_date = {row.work_date: row for row in days_by_user.get(user.id, [])}
        marked = counted_minutes.get(user.id, {})
        plan_days = plan_minutes_total = fact_days = fact_minutes_total = 0
        day_items = []
        for work_date in days_in_range(first, last):
            row = by_date.get(work_date)
            plan = 0
            if row is not None and row.kind == "shift":
                plan = shift_minutes(row.start_time, row.end_time)
            fact = marked.get(work_date, 0) if owners.get((user.id, work_date)) == center.id else 0
            if row is not None and row.kind == "shift" and row.fact_start_time is not None and row.fact_end_time is not None:
                fact = shift_minutes(row.fact_start_time, row.fact_end_time)
            if plan:
                plan_days += 1
                plan_minutes_total += plan
            if fact:
                fact_days += 1
                fact_minutes_total += fact
            day_items.append(
                {"work_date": work_date, "plan_hours": minutes_to_hours(plan), "fact_hours": minutes_to_hours(fact)}
            )
        rate = user.hourly_rate if with_money else None
        rows.append(
            {
                "user_id": user.id,
                "full_name": user.full_name or user.login,
                "role_name": user.role.name,
                "center_name": center.name,
                "pattern": schedule.schedule_pattern if schedule else None,
                "shift_start": format_time(schedule.schedule_start) if schedule else None,
                "shift_end": format_time(schedule.schedule_end) if schedule else None,
                "hourly_rate": float(rate) if rate is not None else None,
                "days": day_items,
                "marks": (marks or {}).get(user.id, []),
                "plan": {
                    "days": plan_days,
                    "hours": minutes_to_hours(plan_minutes_total),
                    "amount": pay_for(plan_minutes_total, rate),
                },
                "fact": {
                    "days": fact_days,
                    "hours": minutes_to_hours(fact_minutes_total),
                    "amount": pay_for(fact_minutes_total, rate),
                },
            }
        )
    return {"year": year, "month": month, "days_in_month": last.day, "center": center_payload(center), "rows": rows}


def fill_pattern_shifts(db: Session, user: User, schedule: StaffCenterSchedule, first: date, last: date) -> int:
    """Ставит смены по шаблону в дни промежутка медцентра, где записи еще нет. Возвращает число добавленных."""
    taken = set(
        db.execute(
            select(StaffScheduleDay.work_date).where(
                StaffScheduleDay.user_id == user.id,
                StaffScheduleDay.center_id == schedule.center_id,
                StaffScheduleDay.work_date.between(first, last),
            )
        ).scalars()
    )
    created = 0
    for work_date, number in pattern_shifts(schedule, first, last):
        if work_date in taken:
            continue
        db.add(
            StaffScheduleDay(
                user_id=user.id,
                center_id=schedule.center_id,
                work_date=work_date,
                kind="shift",
                start_time=schedule.schedule_start,
                end_time=schedule.schedule_end,
                source="pattern",
                shift_no=number,
            )
        )
        created += 1
    return created


def generate_month(db: Session, center: Center, year: int, month: int, *, actor_id: int | None = None) -> dict:
    """«Создать график»: заполняет месяц медцентра для сотрудников с шаблоном и первой сменой.

    Ручной график и уже занятые дни не трогает, поэтому повторное нажатие ничего не ломает.
    """
    first, last = month_bounds(year, month)
    created = 0
    missing = []
    for user in schedule_users(db):
        schedule = user.schedule_in(center.id)
        if schedule is None or not user.is_active or not works_in(user, center.id):
            continue
        if schedule.schedule_anchor_date is None:
            missing.append(user.full_name or user.login)
            continue
        added = fill_pattern_shifts(db, user, schedule, first, last)
        if added:
            audit_schedule_change(
                db,
                staff=user,
                center_id=center.id,
                actor_id=actor_id,
                action="month_generate",
                payload={"center": center.name, "year": year, "month": month, "created": added},
            )
        created += added
    db.commit()
    return {"created": created, "users_without_start": sorted(missing)}


def restart_pattern(db: Session, user: User, schedule: StaffCenterSchedule, work_date: date) -> int:
    """«Назначить первую смену»: цикл медцентра начинается с work_date, авто-смены с этого дня пересчитываются.

    Отгулы, больничные, отпуска и ручные смены остаются. Дни до work_date не меняются.
    """
    schedule.schedule_anchor_date = work_date
    db.execute(
        delete(StaffScheduleDay).where(
            StaffScheduleDay.user_id == user.id,
            StaffScheduleDay.center_id == schedule.center_id,
            StaffScheduleDay.source == "pattern",
            StaffScheduleDay.work_date >= work_date,
        )
    )
    _, last = month_bounds(work_date.year, work_date.month)
    return fill_pattern_shifts(db, user, schedule, work_date, last)


def _center_order(user: User) -> list[int]:
    """Медцентры сотрудника: основной первым, остальные по номеру."""
    ids = {schedule.center_id for schedule in user.center_schedules}
    if user.center_id is not None:
        ids.add(user.center_id)
    return sorted(ids, key=lambda center_id: (center_id != user.center_id, center_id))


def _mark_owners(db: Session, users: list[User], first: date, last: date) -> dict[tuple[int, date], int]:
    """Медцентр, в котором считаются отметки сотрудника за каждый день периода.

    Отметки дня идут в первый медцентр сотрудника, где у него стоит смена в этот день (основной первым),
    а в день без смен — в его первый медцентр. Так один день не попадает в статистику дважды, даже если
    смены стоят в двух медцентрах.
    """
    orders = {user.id: order for user in users if (order := _center_order(user))}
    if not orders:
        return {}
    shift_centers: dict[tuple[int, date], set[int]] = defaultdict(set)
    for user_id, center_id, work_date in db.execute(
        select(StaffScheduleDay.user_id, StaffScheduleDay.center_id, StaffScheduleDay.work_date).where(
            StaffScheduleDay.user_id.in_(list(orders)),
            StaffScheduleDay.work_date.between(first, last),
            StaffScheduleDay.kind == "shift",
            StaffScheduleDay.center_id.is_not(None),
        )
    ):
        shift_centers[(user_id, work_date)].add(center_id)
    owners: dict[tuple[int, date], int] = {}
    for user_id, order in orders.items():
        for work_date in days_in_range(first, last):
            centers = shift_centers.get((user_id, work_date))
            if centers:
                owners[(user_id, work_date)] = next((center_id for center_id in order if center_id in centers), min(centers))
            else:
                owners[(user_id, work_date)] = order[0]
    return owners


def start_plan_if_missing(
    db: Session, user: User, schedule: StaffCenterSchedule, *, actor_id: int | None, today: date | None = None
) -> int:
    """Первая смена по умолчанию: в медцентре есть график, а первой смены нет, — цикл начинается сегодня.

    Ставит смены по шаблону с сегодняшнего дня до конца месяца, чтобы в «Статусе» сразу был план.
    Назначенную первую смену не трогает: ее меняет только «Назначить первую смену». Пишет в журнал
    как «Первая смена назначена». Без графика или с уже назначенной сменой ничего не делает и вернет 0.
    """
    if not schedule.schedule_pattern or schedule.schedule_start is None or schedule.schedule_end is None:
        return 0
    if schedule.schedule_anchor_date is not None:
        return 0
    start = today or local_today()
    _, last = month_bounds(start.year, start.month)
    schedule.schedule_anchor_date = start
    created = fill_pattern_shifts(db, user, schedule, start, last)
    center = db.get(Center, schedule.center_id)
    audit_schedule_change(
        db,
        staff=user,
        center_id=schedule.center_id,
        actor_id=actor_id,
        action="first_shift",
        payload={
            "center": center.name if center else None,
            "work_date": start.isoformat(),
            "anchor_before": None,
            "created": created,
        },
    )
    return created


def _day_row(db: Session, user: User, center_id: int, work_date: date) -> StaffScheduleDay | None:
    return db.execute(
        select(StaffScheduleDay).where(
            StaffScheduleDay.user_id == user.id,
            StaffScheduleDay.center_id == center_id,
            StaffScheduleDay.work_date == work_date,
        )
    ).scalar_one_or_none()


def put_day(db: Session, user: User, center_id: int, work_date: date, kind: str, start: time | None, end: time | None) -> None:
    row = _day_row(db, user, center_id, work_date)
    if row is None:
        row = StaffScheduleDay(user_id=user.id, center_id=center_id, work_date=work_date)
        db.add(row)
    row.kind = kind
    row.start_time = start if kind == "shift" else None
    row.end_time = end if kind == "shift" else None
    if kind != "shift":
        row.fact_start_time = None
        row.fact_end_time = None
    row.source = "manual"


def clear_day(db: Session, user: User, center_id: int, work_date: date) -> int:
    result = db.execute(
        delete(StaffScheduleDay).where(
            StaffScheduleDay.user_id == user.id,
            StaffScheduleDay.center_id == center_id,
            StaffScheduleDay.work_date == work_date,
        )
    )
    return result.rowcount or 0


def put_absence(db: Session, user: User, center_id: int, days: list[date], kind: str) -> int:
    """Отпуск или больничный на период: дни становятся отметкой о неявке, время смены пропадает."""
    existing = {
        row.work_date: row
        for row in db.execute(
            select(StaffScheduleDay).where(
                StaffScheduleDay.user_id == user.id,
                StaffScheduleDay.center_id == center_id,
                StaffScheduleDay.work_date.between(days[0], days[-1]),
            )
        ).scalars()
    }
    for work_date in days:
        row = existing.get(work_date)
        if row is None:
            row = StaffScheduleDay(user_id=user.id, center_id=center_id, work_date=work_date)
            db.add(row)
        row.kind = kind
        row.start_time = None
        row.end_time = None
        row.fact_start_time = None
        row.fact_end_time = None
        row.source = "manual"
    return len(days)


def put_facts(db: Session, user: User, center_id: int, items: list[dict]) -> int:
    """Ручной факт по дням смены. Пустое время снимает правку: факт снова берется из отметок. Проверяем все дни до записи."""
    for item in items:
        if (item["start_time"] is None) != (item["end_time"] is None):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Факт задается сразу с начала и с конца смены")
        if item["start_time"] is not None and item["start_time"] == item["end_time"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Начало и конец факта не должны совпадать")

    dates = [item["work_date"] for item in items]
    existing = {
        row.work_date: row
        for row in db.execute(
            select(StaffScheduleDay).where(
                StaffScheduleDay.user_id == user.id,
                StaffScheduleDay.center_id == center_id,
                StaffScheduleDay.work_date.in_(dates),
            )
        ).scalars()
    }
    for item in items:
        row = existing.get(item["work_date"])
        if row is None or row.kind != "shift":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{item['work_date'].strftime('%d.%m.%Y')} у сотрудника нет смены: факт записывается только в день смены",
            )
    for item in items:
        row = existing[item["work_date"]]
        row.fact_start_time = item["start_time"]
        row.fact_end_time = item["end_time"]
    return len(items)


# Журнал аудита графика: правка графика или ставки пишется в ту же транзакцию, что и сама правка,
# поэтому без записи в журнал правка не сохранится. entity — сотрудник, в payload — было и стало.
# center_id — медцентр, которого касается правка; ставка общая для учетки, для нее — основной медцентр.
def audit_schedule_change(
    db: Session,
    *,
    staff: User,
    center_id: int | None,
    actor_id: int | None,
    action: str,
    payload: dict,
) -> None:
    write_audit_log(
        db,
        entity_type=AUDIT_ENTITY,
        entity_id=staff.id,
        action=action,
        user_id=actor_id,
        center_id=center_id,
        payload_json=payload,
    )


def rate_for_audit(rate: Decimal | None) -> float | None:
    """Ставка в журнале числом: Decimal в JSON не сохраняется."""
    return float(rate) if rate is not None else None


def _day_state(row: StaffScheduleDay | None) -> dict | None:
    if row is None:
        return None
    return {
        "kind": row.kind,
        "start": format_time(row.start_time),
        "end": format_time(row.end_time),
        "fact_start": format_time(row.fact_start_time),
        "fact_end": format_time(row.fact_end_time),
    }


def day_state(db: Session, user: User, center_id: int, work_date: date) -> dict | None:
    """День сотрудника в медцентре в том виде, в каком он попадает в журнал; None — записи нет."""
    return _day_state(_day_row(db, user, center_id, work_date))


def kinds_in_period(db: Session, user: User, center_id: int, days: list[date]) -> dict[str, int]:
    """Сколько дней периода уже заняты чем (shift, dayoff, sick, vacation); без записи — empty."""
    kinds = Counter(
        db.execute(
            select(StaffScheduleDay.kind).where(
                StaffScheduleDay.user_id == user.id,
                StaffScheduleDay.center_id == center_id,
                StaffScheduleDay.work_date.between(days[0], days[-1]),
            )
        ).scalars()
    )
    counts = dict(kinds)
    counts["empty"] = len(days) - sum(kinds.values())
    return counts


def _fact_text(row: StaffScheduleDay) -> str | None:
    if row.fact_start_time is None or row.fact_end_time is None:
        return None
    return f"{format_time(row.fact_start_time)}-{format_time(row.fact_end_time)}"


def facts_state(db: Session, user: User, center_id: int, dates: list[date]) -> dict[date, str | None]:
    """Ручной факт по дням медцентра: «09:30-18:00» или None, когда факт идет из отметок «На работу»."""
    rows = db.execute(
        select(StaffScheduleDay).where(
            StaffScheduleDay.user_id == user.id,
            StaffScheduleDay.center_id == center_id,
            StaffScheduleDay.work_date.in_(dates),
        )
    ).scalars()
    return {row.work_date: _fact_text(row) for row in rows}
