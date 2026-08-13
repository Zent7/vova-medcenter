from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.service import DoctorRole
from app.models.doctor_exam import DoctorExam
from app.schemas.doctor_role import DoctorRoleRead, DoctorRoleUpdate

router = APIRouter()

@router.get("", response_model=list[DoctorRoleRead])
def list_doctor_roles(db: Session = Depends(get_db)) -> list[DoctorRoleRead]:
    roles = db.execute(
        select(DoctorRole)
        .where(DoctorRole.is_active.is_(True))
        .order_by(DoctorRole.sort_order.asc(), DoctorRole.name.asc())
    ).scalars().all()
    return [DoctorRoleRead.model_validate(item) for item in roles]


@router.put("/{role_code}", response_model=DoctorRoleRead)
def update_doctor_role(
    role_code: str,
    payload: DoctorRoleUpdate,
    db: Session = Depends(get_db),
) -> DoctorRoleRead:
    normalized_code = role_code.strip()
    role = db.execute(select(DoctorRole).where(DoctorRole.code == normalized_code)).scalars().first()
    if role is None:
        raise HTTPException(status_code=404, detail="Роль врача не найдена")

    normalized_name = " ".join((payload.full_name or "").split()).strip()
    role.full_name = normalized_name or None
    db.execute(
        update(DoctorExam)
        .where(DoctorExam.doctor_role_id == normalized_code, DoctorExam.deleted_at.is_(None))
        .values(doctor_name=role.full_name)
    )
    db.commit()
    db.refresh(role)
    return DoctorRoleRead.model_validate(role)
