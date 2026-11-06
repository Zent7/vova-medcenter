"""График работы по дням: смены по шаблону, отгулы, больничные, отпуска и фактические часы.

Шаблон сотрудника (`2/2`, `3/3`, `4/4`, `5/2`, `6/1`) задает только порядок: первая смена
цикла ставится кнопкой «Назначить первую смену» (`users.schedule_anchor_date`), дальше дни
считаются от нее без пропусков. «Создать график» заполняет пустые дни нового месяца в том
же порядке, поэтому смена 31 числа и смена 1 числа идут подряд. Ручные записи (время,
отгул, больничный, отпуск) лежат в `staff_schedule_days` и шаблон не сдвигают.
"""

from calendar import monthrange
from collections import defaultdict
from datetime import date, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.center import Center
from app.models.staff_schedule_day import StaffScheduleDay
from app.models.user import Role, User

# Порядок в таблице: сначала операторы, потом врачи; админ попадает в таблицу, только если ему задан график.
SCHEDULE_ROLE_ORDER = ("operator", "doctor", "chairman", "admin")
# Кто открывает график: админ видит и ставки, врач и оператор — только свои медцентры и без денег.
VIEWER_ROLE_CODES = ("admin", "operator", "doctor")
# Цвет медцентра в таблице. Известные коды закреплены за слотом, остальные берут цвет по номеру.
CENTER_PALETTE = ("#2F6FB3", "#2E9E6A", "#D9822B", "#8E5BB5", "#C0504D", "#3A9AA8")
CENTER_PALETTE_SLOTS = {"center-a": 0, "center-b": 1, "center-c": 2}
MINUTES_PER_DAY = 24 * 60
MAX_ABSENCE_DAYS = 366
TWO_PLACES = Decimal("0.01")


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


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


def center_color(center: Center | None) -> str | None:
    if center is None:
        return None
    slot = CENTER_PALETTE_SLOTS.get(center.code, center.id)
    return CENTER_PALETTE[slot % len(CENTER_PALETTE)]


def pattern_shifts(user: User, first: date, last: date) -> list[tuple[date, int]]:
    """Смены по шаблону в промежутке: (день, номер смены). До первой смены цикла шаблон ничего не ставит."""
    if not user.schedule_pattern or user.schedule_anchor_date is None:
        return []
    work, rest = parse_pattern(user.schedule_pattern)
    anchor = user.schedule_anchor_date
    result = []
    for work_date in days_in_range(max(first, anchor), last):
        position = (work_date - anchor).days % (work + rest)
        if position < work:
            result.append((work_date, position + 1))
    return result


def load_schedule_user(db: Session, user_id: int) -> User:
    user = db.execute(
        select(User).options(joinedload(User.role)).where(User.id == user_id)
    ).scalar_one_or_none()
    if user is None or user.role.code not in SCHEDULE_ROLE_ORDER:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден")
    return user


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


def schedule_users(db: Session) -> list[User]:
    return list(
        db.execute(
            select(User)
            .options(joinedload(User.role), joinedload(User.center), selectinload(User.extra_centers))
            .join(Role, User.role_id == Role.id)
            .where(Role.code.in_(SCHEDULE_ROLE_ORDER))
        ).scalars()
    )


def _days_by_user(db: Session, first: date, last: date) -> dict[int, list[StaffScheduleDay]]:
    grouped: dict[int, list[StaffScheduleDay]] = defaultdict(list)
    rows = db.execute(
        select(StaffScheduleDay)
        .where(StaffScheduleDay.work_date.between(first, last))
        .order_by(StaffScheduleDay.work_date)
    ).scalars()
    for row in rows:
        grouped[row.user_id].append(row)
    return grouped


def _sort_key(user: User) -> tuple[int, str, int]:
    return (SCHEDULE_ROLE_ORDER.index(user.role.code), (user.full_name or user.login).lower(), user.id)


def visible_users(users: list[User], days_by_user: dict, viewer_center_ids: set[int] | None) -> list[User]:
    """Кто попадает в таблицу. viewer_center_ids=None — админ видит всех.

    Админ без графика и без записей в таблицу не попадает. Оператор и врач попадают всегда,
    даже с ручным графиком без смен, — им строка нужна, чтобы ее заполнить. Отключенный сотрудник
    остается, пока у него есть записи в этом месяце, — чтобы история не пропала из таблицы.
    """
    result = []
    for user in users:
        has_days = bool(days_by_user.get(user.id))
        if user.role.code == "admin" and user.schedule_pattern is None and not has_days:
            continue
        if not user.is_active and not has_days:
            continue
        if viewer_center_ids is not None and not ({center.id for center in user.work_centers} & viewer_center_ids):
            continue
        result.append(user)
    return sorted(result, key=_sort_key)


def viewer_center_ids(viewer: User) -> set[int] | None:
    if viewer.role.code == "admin":
        return None
    return {center.id for center in viewer.work_centers}


def _day_payload(row: StaffScheduleDay) -> dict:
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
    }


def month_payload(db: Session, viewer: User, year: int, month: int) -> dict:
    """Таблица месяца: сотрудники с днями. Ставки сюда не попадают — их отдает только статистика."""
    first, last = month_bounds(year, month)
    days_by_user = _days_by_user(db, first, last)
    users = visible_users(schedule_users(db), days_by_user, viewer_center_ids(viewer))

    centers: dict[int, dict] = {}
    rows = []
    for user in users:
        center = user.center
        center_data = None
        if center is not None:
            center_data = {"id": center.id, "name": center.name, "color": center_color(center)}
            centers.setdefault(center.id, center_data)
        rows.append(
            {
                "user_id": user.id,
                "full_name": user.full_name or user.login,
                "role_code": user.role.code,
                "role_name": user.role.name,
                "is_active": user.is_active,
                "center": center_data,
                "pattern": user.schedule_pattern,
                "shift_start": format_time(user.schedule_start),
                "shift_end": format_time(user.schedule_end),
                "days": [_day_payload(row) for row in days_by_user.get(user.id, [])],
            }
        )
    return {
        "year": year,
        "month": month,
        "days_in_month": last.day,
        "can_edit": viewer.role.code == "admin",
        "centers": list(centers.values()),
        "rows": rows,
    }


def stats_payload(db: Session, year: int, month: int) -> dict:
    """План и факт по каждому сотруднику за месяц и сумма «часы × ставка». Только для админа."""
    first, last = month_bounds(year, month)
    days_by_user = _days_by_user(db, first, last)
    users = visible_users(schedule_users(db), days_by_user, None)

    rows = []
    for user in users:
        by_date = {row.work_date: row for row in days_by_user.get(user.id, [])}
        plan_days = plan_minutes = fact_days = fact_minutes = 0
        day_items = []
        for work_date in days_in_range(first, last):
            row = by_date.get(work_date)
            plan = fact = 0
            if row is not None and row.kind == "shift":
                plan = shift_minutes(row.start_time, row.end_time)
                if row.fact_start_time is not None and row.fact_end_time is not None:
                    fact = shift_minutes(row.fact_start_time, row.fact_end_time)
                else:
                    fact = plan
            if plan:
                plan_days += 1
                plan_minutes += plan
            if fact:
                fact_days += 1
                fact_minutes += fact
            day_items.append(
                {"work_date": work_date, "plan_hours": minutes_to_hours(plan), "fact_hours": minutes_to_hours(fact)}
            )
        rate = user.hourly_rate
        rows.append(
            {
                "user_id": user.id,
                "full_name": user.full_name or user.login,
                "role_name": user.role.name,
                "center_name": user.center.name if user.center is not None else None,
                "pattern": user.schedule_pattern,
                "shift_start": format_time(user.schedule_start),
                "shift_end": format_time(user.schedule_end),
                "hourly_rate": float(rate) if rate is not None else None,
                "days": day_items,
                "plan": {
                    "days": plan_days,
                    "hours": minutes_to_hours(plan_minutes),
                    "amount": pay_for(plan_minutes, rate),
                },
                "fact": {
                    "days": fact_days,
                    "hours": minutes_to_hours(fact_minutes),
                    "amount": pay_for(fact_minutes, rate),
                },
            }
        )
    return {"year": year, "month": month, "days_in_month": last.day, "rows": rows}


def fill_pattern_shifts(db: Session, user: User, first: date, last: date) -> int:
    """Ставит смены по шаблону в дни промежутка, где записи еще нет. Возвращает число добавленных."""
    if user.schedule_start is None or user.schedule_end is None:
        return 0
    taken = set(
        db.execute(
            select(StaffScheduleDay.work_date).where(
                StaffScheduleDay.user_id == user.id,
                StaffScheduleDay.work_date.between(first, last),
            )
        ).scalars()
    )
    created = 0
    for work_date, number in pattern_shifts(user, first, last):
        if work_date in taken:
            continue
        db.add(
            StaffScheduleDay(
                user_id=user.id,
                work_date=work_date,
                kind="shift",
                start_time=user.schedule_start,
                end_time=user.schedule_end,
                source="pattern",
                shift_no=number,
            )
        )
        created += 1
    return created


def generate_month(db: Session, year: int, month: int) -> dict:
    """«Создать график»: заполняет месяц для всех, у кого выбран шаблон и есть первая смена.

    Ручной график и уже занятые дни не трогает, поэтому повторное нажатие ничего не ломает.
    """
    first, last = month_bounds(year, month)
    created = 0
    missing = []
    for user in schedule_users(db):
        if not user.is_active or not user.schedule_pattern:
            continue
        if user.schedule_anchor_date is None:
            missing.append(user.full_name or user.login)
            continue
        created += fill_pattern_shifts(db, user, first, last)
    db.commit()
    return {"created": created, "users_without_start": sorted(missing)}


def restart_pattern(db: Session, user: User, work_date: date) -> int:
    """«Назначить первую смену»: цикл начинается с work_date, авто-смены с этого дня пересчитываются.

    Отгулы, больничные, отпуска и ручные смены остаются. Дни до work_date не меняются.
    """
    if not user.schedule_pattern:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Сначала задайте график сотруднику кнопкой «График» на странице «Сотрудник»",
        )
    user.schedule_anchor_date = work_date
    db.execute(
        delete(StaffScheduleDay).where(
            StaffScheduleDay.user_id == user.id,
            StaffScheduleDay.source == "pattern",
            StaffScheduleDay.work_date >= work_date,
        )
    )
    _, last = month_bounds(work_date.year, work_date.month)
    return fill_pattern_shifts(db, user, work_date, last)


def put_day(db: Session, user: User, work_date: date, kind: str, start: time | None, end: time | None) -> None:
    row = db.execute(
        select(StaffScheduleDay).where(StaffScheduleDay.user_id == user.id, StaffScheduleDay.work_date == work_date)
    ).scalar_one_or_none()
    if row is None:
        row = StaffScheduleDay(user_id=user.id, work_date=work_date)
        db.add(row)
    row.kind = kind
    row.start_time = start if kind == "shift" else None
    row.end_time = end if kind == "shift" else None
    if kind != "shift":
        row.fact_start_time = None
        row.fact_end_time = None
    row.source = "manual"


def clear_day(db: Session, user: User, work_date: date) -> int:
    result = db.execute(
        delete(StaffScheduleDay).where(
            StaffScheduleDay.user_id == user.id,
            StaffScheduleDay.work_date == work_date,
        )
    )
    return result.rowcount or 0


def put_absence(db: Session, user: User, days: list[date], kind: str) -> int:
    """Отпуск или больничный на период: дни становятся отметкой о неявке, время смены пропадает."""
    existing = {
        row.work_date: row
        for row in db.execute(
            select(StaffScheduleDay).where(
                StaffScheduleDay.user_id == user.id,
                StaffScheduleDay.work_date.between(days[0], days[-1]),
            )
        ).scalars()
    }
    for work_date in days:
        row = existing.get(work_date)
        if row is None:
            row = StaffScheduleDay(user_id=user.id, work_date=work_date)
            db.add(row)
        row.kind = kind
        row.start_time = None
        row.end_time = None
        row.fact_start_time = None
        row.fact_end_time = None
        row.source = "manual"
    return len(days)


def put_facts(db: Session, user: User, items: list[dict]) -> int:
    """Факт по дням смены. Пустые время — «отработано по плану». Проверяем все дни до записи."""
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
