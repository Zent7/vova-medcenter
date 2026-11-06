from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.work_status import WorkStatusMonthRead
from app.services import work_status as service

# Статус «На работу / С работы»: открыт каждому сотруднику, и только для его собственных отметок.
# Маршруты подключены в router.py под /work-status.
router = APIRouter()


def _month_read(db: Session, user: User, year: int | None, month: int | None) -> WorkStatusMonthRead:
    now = service.utc_now()
    today = service.local_today(now)
    payload = service.month_payload(db, user, year or today.year, month or today.month, now)
    return WorkStatusMonthRead.model_validate(payload)


@router.get("/me", response_model=WorkStatusMonthRead)
def read_my_status(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkStatusMonthRead:
    return _month_read(db, current_user, year, month)


@router.post("/start", response_model=WorkStatusMonthRead)
def start_work(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> WorkStatusMonthRead:
    service.start_work(db, current_user, service.utc_now())
    db.commit()
    return _month_read(db, current_user, None, None)


@router.post("/stop", response_model=WorkStatusMonthRead)
def stop_work(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> WorkStatusMonthRead:
    service.stop_work(db, current_user, service.utc_now())
    db.commit()
    return _month_read(db, current_user, None, None)
