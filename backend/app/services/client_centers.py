"""Медцентры клиента: у каждого центра своя клиентская база.

Клиент лежит в одном или нескольких центрах (``client_centers``). Сотрудник
видит клиентов своих центров, а клиент, заведённый сразу в два центра, виден в
обоих. Обращение в центре тоже делает клиента клиентом этого центра: иначе его
строка журнала была бы у сотрудников центра, а карточка — нет.
"""

from collections.abc import Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.center import Center
from app.models.client import Client, client_centers
from app.models.user import User

# Код центра, куда попадают клиенты без явного центра: там жила прежняя программа заказчика.
DEFAULT_CENTER_CODE = "center-a"


def client_in_centers_condition(center_ids: Iterable[int]):
    """Условие «клиент лежит хотя бы в одном из этих центров»."""
    ids = sorted({int(center_id) for center_id in center_ids})
    return Client.id.in_(select(client_centers.c.client_id).where(client_centers.c.center_id.in_(ids)))


def default_center_id(db: Session, user: User | None = None) -> int | None:
    """Центр для клиента, у которого центр не назван: основной центр сотрудника, иначе первый рабочий."""
    pinned_center_id = getattr(user, "pinned_center_id", None)
    if pinned_center_id is not None:
        return pinned_center_id
    by_code = db.scalar(select(Center.id).where(Center.code == DEFAULT_CENTER_CODE, Center.is_active.is_(True)))
    if by_code is not None:
        return by_code
    return db.scalar(select(Center.id).where(Center.is_active.is_(True)).order_by(Center.id.asc()))


def resolve_center_ids(db: Session, center_ids: Iterable[int] | None, user: User | None = None) -> list[int]:
    """Проверенный список центров клиента; не назван — центр по умолчанию.

    В базе без единого центра (пустая установка) клиента некуда отнести: список пуст.
    """
    requested = list(dict.fromkeys(int(center_id) for center_id in (center_ids or [])))
    if not requested:
        fallback = default_center_id(db, user)
        return [] if fallback is None else [fallback]

    found = set(
        db.execute(select(Center.id).where(Center.id.in_(requested), Center.is_active.is_(True))).scalars().all()
    )
    missing = [center_id for center_id in requested if center_id not in found]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Медцентр не найден")
    return sorted(found)


def set_client_centers(db: Session, client: Client, center_ids: Iterable[int]) -> None:
    """Заменяет центры клиента на переданные (центры уже проверены ``resolve_center_ids``)."""
    wanted = {int(center_id) for center_id in center_ids}
    client.centers = list(db.execute(select(Center).where(Center.id.in_(wanted)).order_by(Center.id)).scalars().all())


def ensure_client_in_center(db: Session, client: Client, center_id: int | None) -> None:
    """Добавляет клиента в центр, если его там ещё нет; остальные центры не трогает."""
    if center_id is None or center_id in client.center_ids:
        return
    center = db.get(Center, center_id)
    if center is not None:
        client.centers.append(center)
