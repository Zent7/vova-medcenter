from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.v1.routes.auth import require_admin
from app.core.security import hash_password
from app.db.session import get_db
from app.models.center import Center
from app.models.user import ALL_CENTERS_ROLE_CODE, Role, User
from app.schemas.user_admin import RoleRead, StaffUserCreate, StaffUserRead

router = APIRouter()

STAFF_ROLE_CODES = ("chairman", "doctor", "admin", "operator")
ASSIGNABLE_ROLE_CODES = ("doctor", "admin", "operator")


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
        .options(joinedload(User.role), joinedload(User.center))
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

    center_id = None
    if role.code != ALL_CENTERS_ROLE_CODE:
        if payload.center_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Выберите медцентр сотрудника")
        center = db.get(Center, payload.center_id)
        if center is None or not center.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Медцентр не найден")
        center_id = center.id

    user = User(
        center_id=center_id,
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
