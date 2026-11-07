from datetime import date, time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import get_current_user, require_admin
from app.db.session import get_db
from app.models.center import Center
from app.models.user import User
from app.schemas.work_schedule import (
    WorkScheduleAbsenceCreate,
    WorkScheduleChangeRead,
    WorkScheduleDayUpdate,
    WorkScheduleFactsUpdate,
    WorkScheduleFirstShift,
    WorkScheduleGenerate,
    WorkScheduleGenerateRead,
    WorkScheduleMonthRead,
    WorkScheduleStatsRead,
)
from app.services import work_schedule as service
from app.services import work_status
from app.services.notifications import notify_change

# График работы по медцентрам: таблица месяца открыта админу, врачу и оператору; статистика, ставки и
# все правки — только админу. Каждый запрос называет медцентр (center_id); без него берется первый
# медцентр смотрящего. Маршруты ниже подключены в router.py под /work-schedule.
router = APIRouter()


def require_schedule_viewer(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role.code not in service.VIEWER_ROLE_CODES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="График работы доступен админу, врачу и оператору",
        )
    return current_user


KIND_LABELS = {"shift": "смена", "dayoff": "отгул", "sick": "больничный", "vacation": "отпуск"}


def _day_text(kind: str, start: time | None, end: time | None) -> str:
    if kind == "shift" and start is not None and end is not None:
        return f"смена {service.format_time(start)}-{service.format_time(end)}"
    return KIND_LABELS.get(kind, kind)


def _notify_schedule(
    background_tasks: BackgroundTasks,
    db: Session,
    admin: User,
    staff: User,
    center: Center,
    title: str,
    lines: list[str],
) -> None:
    """Письмо админам об изменении графика сотрудника в медцентре. Вызывать после commit."""
    notify_change(
        background_tasks,
        db,
        title=title,
        actor=admin.full_name or admin.login,
        lines=[f"Сотрудник: {staff.full_name or staff.login}", f"Медцентр: {center.name}", *lines],
    )


@router.get("/month", response_model=WorkScheduleMonthRead)
def read_month(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    center_id: int | None = Query(default=None),
    viewer: User = Depends(require_schedule_viewer),
    db: Session = Depends(get_db),
) -> WorkScheduleMonthRead:
    center = service.pick_center(db, viewer, center_id)
    return WorkScheduleMonthRead.model_validate(service.month_payload(db, viewer, center, year, month))


@router.get("/stats", response_model=WorkScheduleStatsRead)
def read_stats(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    center_id: int | None = Query(default=None),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleStatsRead:
    center = service.pick_center(db, admin, center_id)
    first, last = service.month_bounds(year, month)
    # Факт из отметок «На работу» (ручная правка на смене его заменяет); считается один раз на месяц.
    counted = work_status.fact_minutes_by_user(db, first, last, work_status.utc_now())
    return WorkScheduleStatsRead.model_validate(service.stats_payload(db, center, year, month, counted))


@router.post("/month/generate", response_model=WorkScheduleGenerateRead)
def generate_month(
    payload: WorkScheduleGenerate,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleGenerateRead:
    center = service.pick_center(db, admin, payload.center_id)
    result = service.generate_month(db, center, payload.year, payload.month, actor_id=admin.id)
    if result["created"]:
        lines = [
            f"Медцентр: {center.name}",
            f"Месяц: {payload.month:02d}.{payload.year}",
            f"Создано смен: {result['created']}",
        ]
        if result["users_without_start"]:
            lines.append("Не назначена первая смена: " + ", ".join(result["users_without_start"]))
        notify_change(
            background_tasks,
            db,
            title="Создан график работы",
            actor=admin.full_name or admin.login,
            lines=lines,
        )
    return WorkScheduleGenerateRead(**result)


@router.put("/{user_id}/days/{work_date}", response_model=WorkScheduleChangeRead)
def update_day(
    user_id: int,
    work_date: date,
    payload: WorkScheduleDayUpdate,
    background_tasks: BackgroundTasks,
    center_id: int = Query(),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleChangeRead:
    user = service.load_schedule_user(db, user_id)
    center = service.load_schedule_center(db, user, center_id)
    service.check_day_update(payload.kind, payload.start_time, payload.end_time)
    before = service.day_state(db, user, center.id, work_date)
    service.put_day(db, user, center.id, work_date, payload.kind, payload.start_time, payload.end_time)
    db.flush()
    after = service.day_state(db, user, center.id, work_date)
    if before != after:
        service.audit_schedule_change(
            db,
            staff=user,
            center_id=center.id,
            actor_id=admin.id,
            action="day_update",
            payload={"center": center.name, "date": work_date.isoformat(), "before": before, "after": after},
        )
    db.commit()
    _notify_schedule(
        background_tasks,
        db,
        admin,
        user,
        center,
        "Изменен график работы",
        [
            f"Дата: {work_date:%d.%m.%Y}",
            f"Стало: {_day_text(payload.kind, payload.start_time, payload.end_time)}",
        ],
    )
    return WorkScheduleChangeRead(changed=1)


@router.delete("/{user_id}/days/{work_date}", response_model=WorkScheduleChangeRead)
def clear_day(
    user_id: int,
    work_date: date,
    background_tasks: BackgroundTasks,
    center_id: int = Query(),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleChangeRead:
    user = service.load_schedule_user(db, user_id)
    center = service.load_schedule_center(db, user, center_id)
    before = service.day_state(db, user, center.id, work_date)
    changed = service.clear_day(db, user, center.id, work_date)
    if changed:
        service.audit_schedule_change(
            db,
            staff=user,
            center_id=center.id,
            actor_id=admin.id,
            action="day_clear",
            payload={"center": center.name, "date": work_date.isoformat(), "before": before, "after": None},
        )
    db.commit()
    if changed:
        _notify_schedule(
            background_tasks,
            db,
            admin,
            user,
            center,
            "Изменен график работы",
            [f"Дата: {work_date:%d.%m.%Y}", "Стало: день очищен, смены нет"],
        )
    return WorkScheduleChangeRead(changed=changed)


@router.post("/{user_id}/absences", response_model=WorkScheduleChangeRead)
def add_absence(
    user_id: int,
    payload: WorkScheduleAbsenceCreate,
    background_tasks: BackgroundTasks,
    center_id: int = Query(),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleChangeRead:
    user = service.load_schedule_user(db, user_id)
    center = service.load_schedule_center(db, user, center_id)
    days = service.check_absence_period(payload.date_from, payload.date_to)
    before = service.kinds_in_period(db, user, center.id, days)
    changed = service.put_absence(db, user, center.id, days, payload.kind)
    # Дни, которые уже стоят в этом виде, не меняются: если стоят все, в журнал ничего не пишем.
    already_kind_days = before.get(payload.kind, 0)
    if already_kind_days != len(days):
        service.audit_schedule_change(
            db,
            staff=user,
            center_id=center.id,
            actor_id=admin.id,
            action="absence_add",
            payload={
                "center": center.name,
                "from": days[0].isoformat(),
                "to": days[-1].isoformat(),
                "kind": payload.kind,
                "days": len(days) - already_kind_days,
                "before": before,
            },
        )
    db.commit()
    if changed:
        _notify_schedule(
            background_tasks,
            db,
            admin,
            user,
            center,
            "Изменен график работы",
            [
                f"Период: с {days[0]:%d.%m.%Y} по {days[-1]:%d.%m.%Y}",
                f"Стало: {KIND_LABELS.get(payload.kind, payload.kind)}",
            ],
        )
    return WorkScheduleChangeRead(changed=changed)


@router.post("/{user_id}/first-shift", response_model=WorkScheduleChangeRead)
def start_first_shift(
    user_id: int,
    payload: WorkScheduleFirstShift,
    background_tasks: BackgroundTasks,
    center_id: int = Query(),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleChangeRead:
    user = service.load_schedule_user(db, user_id)
    center = service.load_schedule_center(db, user, center_id)
    schedule = user.schedule_in(center.id)
    if schedule is None or not schedule.schedule_pattern:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Сначала задайте график сотруднику в этом медцентре в разделе «Сотрудники»",
        )
    anchor_before = schedule.schedule_anchor_date
    created = service.restart_pattern(db, user, schedule, payload.work_date)
    service.audit_schedule_change(
        db,
        staff=user,
        center_id=center.id,
        actor_id=admin.id,
        action="first_shift",
        payload={
            "center": center.name,
            "work_date": payload.work_date.isoformat(),
            "anchor_before": anchor_before.isoformat() if anchor_before else None,
            "created": created,
        },
    )
    db.commit()
    _notify_schedule(
        background_tasks,
        db,
        admin,
        user,
        center,
        "Изменен график работы",
        [
            f"Первая смена: {payload.work_date:%d.%m.%Y}",
            f"График: {schedule.schedule_pattern}, {service.format_time(schedule.schedule_start)}-{service.format_time(schedule.schedule_end)}",
            f"Создано смен: {created}",
        ],
    )
    return WorkScheduleChangeRead(changed=created)


@router.put("/{user_id}/facts", response_model=WorkScheduleChangeRead)
def update_facts(
    user_id: int,
    payload: WorkScheduleFactsUpdate,
    background_tasks: BackgroundTasks,
    center_id: int = Query(),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleChangeRead:
    user = service.load_schedule_user(db, user_id)
    center = service.load_schedule_center(db, user, center_id)
    items = [item.model_dump() for item in payload.items]
    fact_dates = list(dict.fromkeys(item["work_date"] for item in items))
    facts_before = service.facts_state(db, user, center.id, fact_dates)
    changed = service.put_facts(db, user, center.id, items)
    db.flush()
    facts_after = service.facts_state(db, user, center.id, fact_dates)
    fact_changes = [
        {"date": work_date.isoformat(), "before": facts_before.get(work_date), "after": facts_after.get(work_date)}
        for work_date in fact_dates
        if facts_before.get(work_date) != facts_after.get(work_date)
    ]
    if fact_changes:
        service.audit_schedule_change(
            db,
            staff=user,
            center_id=center.id,
            actor_id=admin.id,
            action="facts_update",
            payload={"center": center.name, "items": fact_changes},
        )
    db.commit()
    if changed:
        lines = [
            f"{item['work_date']:%d.%m.%Y}: "
            + (
                f"факт {service.format_time(item['start_time'])}-{service.format_time(item['end_time'])}"
                if item["start_time"] is not None
                else "факт по отметкам «На работу»"
            )
            for item in items
        ]
        _notify_schedule(background_tasks, db, admin, user, center, "Изменено фактическое время работы", lines)
    return WorkScheduleChangeRead(changed=changed)
