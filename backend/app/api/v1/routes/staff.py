from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.v1.routes.auth import require_admin
from app.core.security import generate_session_epoch, hash_password
from app.db.session import get_db
from app.models.center import Center
from app.models.user import ALL_CENTERS_ROLE_CODE, Role, User
from app.schemas.user_admin import RoleRead, StaffCentersUpdate, StaffUserCreate, StaffUserRead

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
        .options(joinedload(User.role), joinedload(User.center), selectinload(User.extra_centers))
        .join(Role)
        .where(Role.code.in_(STAFF_ROLE_CODES))
        .order_by(User.is_active.desc(), User.full_name.asc(), User.id.asc())
    ).scalars().all()
    return [StaffUserRead.model_validate(user) for user in users]


@router.post("", response_model=StaffUserRead, status_code=status.HTTP_201_CREATED)
def create_staff(
    payload: StaffUserCreate,
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

    user = User(
        center_id=centers[0].id if centers else None,
        extra_centers=centers[1:],
        role_id=role.id,
        login=payload.login,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        email=payload.email,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.refresh(user, attribute_names=["role"])
    return StaffUserRead.model_validate(user)


@router.put("/{user_id}/centers", response_model=StaffUserRead)
def update_staff_centers(
    user_id: int,
    payload: StaffCentersUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StaffUserRead:
    """Задаёт центры существующего сотрудника: первый основной, остальные дополнительные."""
    user = db.execute(
        select(User)
        .options(joinedload(User.role), joinedload(User.center), selectinload(User.extra_centers))
        .where(User.id == user_id)
    ).scalar_one_or_none()
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


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_staff_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    user = db.execute(
        select(User)
        .options(joinedload(User.role))
        .where(User.id == user_id)
    ).scalar_one_or_none()
    if user is None or user.role.code not in STAFF_ROLE_CODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден")
    if user.id == current_user.id or user.role.code == "chairman":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя удалить председателя или свою учетную запись")

    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
