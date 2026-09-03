from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.center import Center
from app.models.doctor_exam import DoctorExam
from app.models.encounter import Encounter
from app.models.service import DoctorRole
from app.schemas.doctor_role import DoctorRoleRead, DoctorRoleUpdate
from app.services.doctor_directory import get_center_doctor_names, set_center_doctor_name

router = APIRouter()


def _require_center(db: Session, center_id: int) -> Center:
    center = db.get(Center, center_id)
    if center is None:
        raise HTTPException(status_code=404, detail="Медцентр не найден")
    return center


@router.get("", response_model=list[DoctorRoleRead])
def list_doctor_roles(
    center_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[DoctorRoleRead]:
    """Специальности врачей с ФИО того медцентра, который спросили.

    Специальности общие, ФИО у каждого центра своё. Без `center_id` имена не
    подставляются: общего справочника врачей на всю базу больше нет.
    """

    roles = db.execute(
        select(DoctorRole)
        .where(DoctorRole.is_active.is_(True))
        .order_by(DoctorRole.sort_order.asc(), DoctorRole.name.asc())
    ).scalars().all()
    names_by_code = get_center_doctor_names(db, center_id)
    return [
        DoctorRoleRead(
            id=role.id,
            code=role.code,
            name=role.name,
            full_name=names_by_code.get(str(role.code).strip()) or None,
            sort_order=role.sort_order,
            is_active=role.is_active,
        )
        for role in roles
    ]


@router.put("/{role_code}", response_model=DoctorRoleRead)
def update_doctor_role(
    role_code: str,
    payload: DoctorRoleUpdate,
    center_id: int = Query(...),
    db: Session = Depends(get_db),
) -> DoctorRoleRead:
    """Задаёт ФИО врача для одного медцентра, не трогая остальные."""

    normalized_code = role_code.strip()
    role = db.execute(select(DoctorRole).where(DoctorRole.code == normalized_code)).scalars().first()
    if role is None:
        raise HTTPException(status_code=404, detail="Роль врача не найдена")
    _require_center(db, center_id)

    saved_name = set_center_doctor_name(db, center_id, normalized_code, payload.full_name)

    # Уже сохранённые осмотры переподписываем только в этом медцентре: осмотры
    # соседнего центра вёл другой врач, и переписать их было бы подлогом.
    center_encounter_ids = select(Encounter.id).where(Encounter.center_id == center_id)
    db.execute(
        update(DoctorExam)
        .where(
            DoctorExam.doctor_role_id == normalized_code,
            DoctorExam.deleted_at.is_(None),
            DoctorExam.encounter_id.in_(center_encounter_ids),
        )
        .values(doctor_name=saved_name)
    )
    db.commit()

    return DoctorRoleRead(
        id=role.id,
        code=role.code,
        name=role.name,
        full_name=saved_name,
        sort_order=role.sort_order,
        is_active=role.is_active,
    )
