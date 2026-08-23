from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.center import Center
from app.schemas.center import CenterNumberingRead, CenterNumberingUpdate, CenterRead
from app.services.document_generator import lmk_certificate_next_number

router = APIRouter()


@router.get("", response_model=list[CenterRead])
def list_centers(db: Session = Depends(get_db)) -> list[CenterRead]:
    items = db.execute(
        select(Center).where(Center.is_active.is_(True)).order_by(Center.name.asc(), Center.id.asc())
    ).scalars().all()
    return [CenterRead.model_validate(item) for item in items]


def _numbering_response(db: Session, center: Center) -> CenterNumberingRead:
    return CenterNumberingRead(
        center_id=center.id,
        lmk_certificate_last_number=center.lmk_certificate_last_number,
        lmk_certificate_next_number=lmk_certificate_next_number(db, center.id),
    )


def _get_center(db: Session, center_id: int) -> Center:
    center = db.get(Center, center_id)
    if center is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Медцентр не найден")
    return center


@router.get("/{center_id}/numbering", response_model=CenterNumberingRead)
def read_center_numbering(center_id: int, db: Session = Depends(get_db)) -> CenterNumberingRead:
    """Нумерация справок ЛМК медцентра: последний бумажный и следующий номер."""

    return _numbering_response(db, _get_center(db, center_id))


@router.patch("/{center_id}/numbering", response_model=CenterNumberingRead)
def update_center_numbering(
    center_id: int,
    payload: CenterNumberingUpdate,
    db: Session = Depends(get_db),
) -> CenterNumberingRead:
    """Задаёт последний номер справки ЛМК из бумажного журнала медцентра."""

    center = _get_center(db, center_id)
    center.lmk_certificate_last_number = payload.lmk_certificate_last_number
    db.commit()
    db.refresh(center)
    return _numbering_response(db, center)
