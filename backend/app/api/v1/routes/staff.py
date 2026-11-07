from datetime import date, time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.v1.routes.auth import require_admin
from app.core.security import generate_session_epoch, hash_password
from app.db.session import get_db
from app.models.center import Center
from app.models.staff_center_schedule import StaffCenterSchedule
from app.models.user import ALL_CENTERS_ROLE_CODE, Role, User
from app.schemas.user_admin import (
    RoleRead,
    StaffCenterScheduleCreate,
    StaffCentersUpdate,
    StaffEmailUpdate,
    StaffScheduleUpdate,
    StaffUserCreate,
    StaffUserDeleteResponse,
    StaffUserRead,
)
from app.services.audit import write_audit_log
from app.services.notifications import notify_change
from app.services.work_schedule import AUDIT_ENTITY, audit_schedule_change, rate_for_audit, start_plan_if_missing

router = APIRouter()

STAFF_ROLE_CODES = ("chairman", "doctor", "admin", "operator")
ASSIGNABLE_ROLE_CODES = ("doctor", "admin", "operator")


def resolve_work_centers(db: Session, center_ids: list[int]) -> list[Center]:
    """Центры сотрудника в порядке запроса, первый — основной; повторы отбрасываются."""
    unique_ids = list(dict.fromkeys(center_ids))
    if not unique_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Выберите медцентр сотрудника")
    centers = []
    for center_id in unique_ids:
        center = db.get(Center, center_id)
        if center is None or not center.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Медцентр не найден")
        centers.append(center)
    return centers


def check_schedule_centers(allowed_center_ids: set[int], schedules: list[StaffCenterScheduleCreate]) -> None:
    """График задают только в медцентрах сотрудника и не больше одного на медцентр; админу графика нет."""
    ids = [item.center_id for item in schedules]
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Медцентр в графиках указан дважды")
    for center_id in ids:
        if center_id not in allowed_center_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="График можно задать только в медцентре, где работает сотрудник",
            )


def describe_schedule(pattern: str | None, start: time | None, end: time | None) -> str:
    """Строка графика для письма и журнала: «2/2, 09:00-20:00» или «без графика»."""
    if pattern is None or start is None or end is None:
        return "без графика"
    return f"{pattern}, {start:%H:%M}-{end:%H:%M}"


def _staff_options():
    return (
        joinedload(User.role),
        joinedload(User.center),
        selectinload(User.extra_centers),
        selectinload(User.center_schedules),
    )


@router.get("/roles", response_model=list[RoleRead])
def list_staff_roles(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[RoleRead]:
    roles = db.execute(select(Role).where(Role.code.in_(ASSIGNABLE_ROLE_CODES))).scalars().all()
    order = {code: index for index, code in enumerate(ASSIGNABLE_ROLE_CODES)}
    roles.sort(key=lambda item: order.get(item.code, 999))
    return [RoleRead.model_validate(role) for role in roles]


@router.get("", response_model=list[StaffUserRead])
def list_staff(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[StaffUserRead]:
    users = db.execute(
        select(User)
        .options(*_staff_options())
        .join(Role)
        .where(Role.code.in_(STAFF_ROLE_CODES))
        .order_by(User.is_active.desc(), User.full_name.asc(), User.id.asc())
    ).unique().scalars().all()
    return [StaffUserRead.model_validate(user) for user in users]


@router.post("", response_model=StaffUserRead, status_code=status.HTTP_201_CREATED)
def create_staff(
    payload: StaffUserCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StaffUserRead:
    existing_user = db.execute(select(User).where(User.login == payload.login)).scalar_one_or_none()
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Логин уже занят")

    role = db.execute(select(Role).where(Role.code == payload.role_code)).scalar_one_or_none()
    if role is None or role.code not in ASSIGNABLE_ROLE_CODES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимая роль сотрудника")

    centers = [] if role.code == ALL_CENTERS_ROLE_CODE else resolve_work_centers(db, payload.requested_center_ids)
    check_schedule_centers({center.id for center in centers}, payload.schedules)
    center_names = {center.id: center.name for center in centers}

    user = User(
        center_id=centers[0].id if centers else None,
        extra_centers=centers[1:],
        role_id=role.id,
        login=payload.login,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        email=payload.email,
        is_active=True,
        hourly_rate=payload.hourly_rate,
    )
    db.add(user)
    db.flush()
    first_shifts: dict[int, date] = {}
    for item in payload.schedules:
        schedule_row = StaffCenterSchedule(
            center_id=item.center_id,
            schedule_pattern=item.pattern,
            schedule_start=item.shift_start,
            schedule_end=item.shift_end,
        )
        user.center_schedules.append(schedule_row)
        audit_schedule_change(
            db,
            staff=user,
            center_id=item.center_id,
            actor_id=current_user.id,
            action="schedule_create",
            payload={
                "staff": user.full_name or user.login,
                "center": center_names[item.center_id],
                "schedule": describe_schedule(item.pattern, item.shift_start, item.shift_end),
                "hourly_rate": rate_for_audit(user.hourly_rate),
            },
        )
        # Без первой смены график медцентра начинается сегодня, чтобы в «Статусе» сразу был план.
        start_plan_if_missing(db, user, schedule_row, actor_id=current_user.id)
        if schedule_row.schedule_anchor_date is not None:
            first_shifts[item.center_id] = schedule_row.schedule_anchor_date
    db.commit()
    db.refresh(user)
    db.refresh(user, attribute_names=["role"])
    if payload.schedules:
        lines = [f"Сотрудник: {user.full_name or user.login}"]
        for item in payload.schedules:
            lines.append(
                f"Медцентр: {center_names[item.center_id]}, график: "
                f"{describe_schedule(item.pattern, item.shift_start, item.shift_end)}"
            )
            if item.center_id in first_shifts:
                lines.append(f"Первая смена: {first_shifts[item.center_id]:%d.%m.%Y}")
        notify_change(
            background_tasks,
            db,
            title="Создан график работы",
            actor=current_user.full_name or current_user.login,
            lines=lines,
        )
    return StaffUserRead.model_validate(user)


@router.put("/{user_id}/centers", response_model=StaffUserRead)
def update_staff_centers(
    user_id: int,
    payload: StaffCentersUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StaffUserRead:
    """Задаёт центры существующего сотрудника: первый основной, остальные дополнительные.

    Графики и дни в центрах, которые забрали, не стираются: вернувшийся центр получит их обратно.
    """
    user = db.execute(select(User).options(*_staff_options()).where(User.id == user_id)).unique().scalar_one_or_none()
    if user is None or user.role.code not in STAFF_ROLE_CODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден")
    if user.sees_all_centers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Админ видит все медцентры")

    centers = resolve_work_centers(db, payload.center_ids)
    if [center.id for center in centers] != [center.id for center in user.work_centers]:
        user.center_id = centers[0].id
        user.extra_centers = centers[1:]
        # Интерфейс узнаёт свои центры при входе: открытый сеанс завершается, чтобы
        # забранный центр не остался доступен до выхода.
        user.session_epoch = generate_session_epoch()
        db.commit()
        db.refresh(user)
    return StaffUserRead.model_validate(user)


@router.put("/{user_id}/schedules", response_model=StaffUserRead)
def update_staff_schedules(
    user_id: int,
    payload: StaffScheduleUpdate,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StaffUserRead:
    """Задаёт графики сотрудника по медцентрам и ставку; медцентр без графика в запросе его снимает."""
    user = db.execute(select(User).options(*_staff_options()).where(User.id == user_id)).unique().scalar_one_or_none()
    if user is None or user.role.code not in STAFF_ROLE_CODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден")

    work_centers = {center.id: center.name for center in user.work_centers}
    check_schedule_centers(set(work_centers), payload.schedules)
    wanted = {item.center_id: item for item in payload.schedules}
    existing = {item.center_id: item for item in user.center_schedules}
    staff_name = user.full_name or user.login
    changes: list[tuple[str, str, str]] = []  # (центр, было, стало)
    first_shifts: list[tuple[str, date]] = []  # (центр, первая смена, которую поставило сохранение)

    # Меняются только медцентры сотрудника; графики медцентров, которые его не касаются, не трогаем.
    for center_id, center_name in work_centers.items():
        row = existing.get(center_id)
        item = wanted.get(center_id)
        before = describe_schedule(row.schedule_pattern, row.schedule_start, row.schedule_end) if row else "без графика"
        after = describe_schedule(item.pattern, item.shift_start, item.shift_end) if item else "без графика"
        schedule_row = row
        if row is None and item is not None:
            schedule_row = StaffCenterSchedule(
                center_id=center_id,
                schedule_pattern=item.pattern,
                schedule_start=item.shift_start,
                schedule_end=item.shift_end,
            )
            user.center_schedules.append(schedule_row)
        elif row is not None and item is None:
            user.center_schedules.remove(row)
            schedule_row = None
        elif row is not None and item is not None:
            if (row.schedule_pattern, row.schedule_start, row.schedule_end) != (item.pattern, item.shift_start, item.shift_end):
                row.schedule_pattern = item.pattern
                row.schedule_start = item.shift_start
                row.schedule_end = item.shift_end
        if before != after:
            changes.append((center_name, before, after))
            audit_schedule_change(
                db,
                staff=user,
                center_id=center_id,
                actor_id=admin.id,
                action="schedule_update",
                payload={"staff": staff_name, "center": center_name, "before": before, "after": after},
            )
        # Сохранили график без первой смены — она ставится на сегодня; назначенную не трогаем.
        if schedule_row is not None:
            anchor_before = schedule_row.schedule_anchor_date
            start_plan_if_missing(db, user, schedule_row, actor_id=admin.id)
            if anchor_before is None and schedule_row.schedule_anchor_date is not None:
                first_shifts.append((center_name, schedule_row.schedule_anchor_date))

    rate_before = user.hourly_rate
    user.hourly_rate = payload.hourly_rate
    if rate_before != user.hourly_rate:
        audit_schedule_change(
            db,
            staff=user,
            center_id=user.center_id,
            actor_id=admin.id,
            action="rate_update",
            payload={
                "staff": staff_name,
                "before": rate_for_audit(rate_before),
                "after": rate_for_audit(user.hourly_rate),
            },
        )
    db.commit()
    if changes or first_shifts:
        notify_change(
            background_tasks,
            db,
            title="Изменено время работы",
            actor=admin.full_name or admin.login,
            lines=[f"Сотрудник: {staff_name}"]
            + [f"Медцентр: {name}, было: {before}, стало: {after}" for name, before, after in changes]
            + [f"Медцентр: {name}, первая смена: {anchor:%d.%m.%Y}" for name, anchor in first_shifts],
        )
    db.refresh(user)
    return StaffUserRead.model_validate(user)


@router.put("/{user_id}/email", response_model=StaffUserRead)
def update_staff_email(
    user_id: int,
    payload: StaffEmailUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StaffUserRead:
    """Почта сотрудника: на нее приходят уведомления админам; пустое значение ее убирает."""
    user = db.execute(select(User).options(*_staff_options()).where(User.id == user_id)).unique().scalar_one_or_none()
    if user is None or user.role.code not in STAFF_ROLE_CODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден")

    user.email = payload.email
    db.commit()
    db.refresh(user)
    return StaffUserRead.model_validate(user)


@router.delete("/{user_id}", response_model=StaffUserDeleteResponse)
def delete_staff_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StaffUserDeleteResponse:
    """Удаляет учетную запись; если по ней есть записи в программе, только отключает ее."""
    user = db.execute(
        select(User)
        .options(joinedload(User.role), selectinload(User.center_schedules))
        .where(User.id == user_id)
    ).unique().scalar_one_or_none()
    if user is None or user.role.code not in STAFF_ROLE_CODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден")
    if user.id == current_user.id or user.role.code == "chairman":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя удалить председателя или свою учетную запись")

    # Учетка с графиками или ставкой уйдет вместе с ними: запоминаем, что пропадает, и пишем в журнал
    # только если удаление прошло. При отключении (записи в программе) графики остаются на месте.
    lost_schedule = None
    if user.center_schedules or user.hourly_rate is not None:
        lost_schedule = {
            "staff": user.full_name or user.login,
            "schedule": "; ".join(
                f"{item.center_name}: {describe_schedule(item.schedule_pattern, item.schedule_start, item.schedule_end)}"
                for item in user.center_schedules
            ),
            "hourly_rate": rate_for_audit(user.hourly_rate),
        }
    staff_id, staff_center_id = user.id, user.center_id

    try:
        db.delete(user)
        db.flush()
    except IntegrityError:
        # На учетную запись ссылаются клиенты, документы, бланки или журнал аудита.
        # Стереть ее нельзя, иначе пропадет история работы, поэтому только отключаем.
        db.rollback()
        user = db.get(User, user_id)
        user.is_active = False
        db.commit()
        return StaffUserDeleteResponse(
            deleted=False,
            message="Учетную запись нельзя удалить: по ней есть записи в программе. Она отключена и больше не сможет войти.",
        )

    if lost_schedule is not None:
        write_audit_log(
            db,
            entity_type=AUDIT_ENTITY,
            entity_id=staff_id,
            action="staff_delete",
            user_id=current_user.id,
            center_id=staff_center_id,
            payload_json=lost_schedule,
        )
    db.commit()
    return StaffUserDeleteResponse(deleted=True, message="Учетная запись удалена.")
