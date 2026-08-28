import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import generate_session_epoch, verify_password
from app.db.session import SessionLocal, get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, LogoutAllResponse
from app.services.audit import write_audit_log

router = APIRouter()

TOKEN_PREFIX = "demo-token-"
SESSION_MANAGER_ROLE_CODES = ("chairman", "admin")
SESSION_ENDED_DETAIL = "Сеанс завершен, войдите заново"


def build_access_token(user: User) -> str:
    return f"{TOKEN_PREFIX}{user.id}.{user.session_epoch}"


def get_optional_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User | None:
    if authorization is None:
        return None
    return get_current_user(authorization=authorization, db=db)


def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")

    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith(TOKEN_PREFIX):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Некорректный токен")

    user_part, separator, session_epoch = token.removeprefix(TOKEN_PREFIX).partition(".")
    try:
        user_id = int(user_part)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Некорректный токен") from exc

    # Токен без метки сеанса выдан старой версией сервера: считаем его завершенным.
    if not separator or not session_epoch:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SESSION_ENDED_DETAIL)

    user = db.execute(select(User).where(User.id == user_id, User.is_active.is_(True))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    if not secrets.compare_digest(user.session_epoch or "", session_epoch):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SESSION_ENDED_DETAIL)
    return user


def require_session_manager(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role.code not in SESSION_MANAGER_ROLE_CODES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Завершать сеансы может только председатель или админ",
        )
    return current_user


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.login == payload.login, User.is_active.is_(True))).scalar_one_or_none()
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")

        if not user.session_epoch:
            user.session_epoch = generate_session_epoch()
        user.last_login_at = datetime.now(timezone.utc)
        db.add(user)
        db.commit()
        db.refresh(user, attribute_names=["role"])

        return LoginResponse(
            user_id=user.id,
            access_token=build_access_token(user),
            user_name=user.full_name,
            role_code=user.role.code,
            role_name=user.role.name,
        )


@router.post("/logout-all", response_model=LogoutAllResponse)
def logout_all_sessions(
    current_user: User = Depends(require_session_manager),
    db: Session = Depends(get_db),
) -> LogoutAllResponse:
    """Завершает сеансы всех сотрудников, включая того, кто нажал кнопку."""
    users = db.execute(select(User)).scalars().all()
    for user in users:
        user.session_epoch = generate_session_epoch()

    write_audit_log(
        db,
        entity_type="user_session",
        entity_id=current_user.id,
        action="logout_all",
        user_id=current_user.id,
        center_id=current_user.center_id,
        payload_json={"ended_sessions": len(users)},
    )
    db.commit()
    return LogoutAllResponse(ended_sessions=len(users))
