from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import get_current_user, require_admin
from app.db.session import get_db
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

# График работы: таблица месяца открыта админу, врачу и оператору; статистика, ставки и
# все правки — только админу. Маршруты ниже подключены в router.py под /work-schedule.
router = APIRouter()


def require_schedule_viewer(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role.code not in service.VIEWER_ROLE_CODES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="График работы доступен админу, врачу и оператору",
        )
    return current_user


@router.get("/month", response_model=WorkScheduleMonthRead)
def read_month(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    viewer: User = Depends(require_schedule_viewer),
    db: Session = Depends(get_db),
) -> WorkScheduleMonthRead:
    return WorkScheduleMonthRead.model_validate(service.month_payload(db, viewer, year, month))


@router.get("/stats", response_model=WorkScheduleStatsRead)
def read_stats(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleStatsRead:
    return WorkScheduleStatsRead.model_validate(service.stats_payload(db, year, month))


@router.post("/month/generate", response_model=WorkScheduleGenerateRead)
def generate_month(
    payload: WorkScheduleGenerate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleGenerateRead:
    return WorkScheduleGenerateRead(**service.generate_month(db, payload.year, payload.month))


@router.put("/{user_id}/days/{work_date}", response_model=WorkScheduleChangeRead)
def update_day(
    user_id: int,
    work_date: date,
    payload: WorkScheduleDayUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleChangeRead:
    user = service.load_schedule_user(db, user_id)
    service.check_day_update(payload.kind, payload.start_time, payload.end_time)
    service.put_day(db, user, work_date, payload.kind, payload.start_time, payload.end_time)
    db.commit()
    return WorkScheduleChangeRead(changed=1)


@router.delete("/{user_id}/days/{work_date}", response_model=WorkScheduleChangeRead)
def clear_day(
    user_id: int,
    work_date: date,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleChangeRead:
    user = service.load_schedule_user(db, user_id)
    changed = service.clear_day(db, user, work_date)
    db.commit()
    return WorkScheduleChangeRead(changed=changed)


@router.post("/{user_id}/absences", response_model=WorkScheduleChangeRead)
def add_absence(
    user_id: int,
    payload: WorkScheduleAbsenceCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleChangeRead:
    user = service.load_schedule_user(db, user_id)
    days = service.check_absence_period(payload.date_from, payload.date_to)
    changed = service.put_absence(db, user, days, payload.kind)
    db.commit()
    return WorkScheduleChangeRead(changed=changed)


@router.post("/{user_id}/first-shift", response_model=WorkScheduleChangeRead)
def start_first_shift(
    user_id: int,
    payload: WorkScheduleFirstShift,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleChangeRead:
    user = service.load_schedule_user(db, user_id)
    created = service.restart_pattern(db, user, payload.work_date)
    db.commit()
    return WorkScheduleChangeRead(changed=created)


@router.put("/{user_id}/facts", response_model=WorkScheduleChangeRead)
def update_facts(
    user_id: int,
    payload: WorkScheduleFactsUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkScheduleChangeRead:
    user = service.load_schedule_user(db, user_id)
    items = [item.model_dump() for item in payload.items]
    changed = service.put_facts(db, user, items)
    db.commit()
    return WorkScheduleChangeRead(changed=changed)
