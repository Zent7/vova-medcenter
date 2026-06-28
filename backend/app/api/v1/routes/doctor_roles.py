from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.service import DoctorRole
from app.schemas.doctor_role import DoctorRoleRead

router = APIRouter()

@router.get("", response_model=list[DoctorRoleRead])
def list_doctor_roles(db: Session = Depends(get_db)) -> list[DoctorRoleRead]:
    roles = db.execute(
        select(DoctorRole)
        .where(DoctorRole.is_active.is_(True))
        .order_by(DoctorRole.sort_order.asc(), DoctorRole.name.asc())
    ).scalars().all()
    return [DoctorRoleRead.model_validate(item) for item in roles]
