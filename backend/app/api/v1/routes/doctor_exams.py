from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.client import Client
from app.models.doctor_exam import DoctorExam
from app.models.encounter import Encounter
from app.schemas.doctor_exam import DoctorExamCreate, DoctorExamRead, DoctorExamUpdate
from app.services.audit import write_audit_log

router = APIRouter()


def validate_links(db: Session, client_id: int, encounter_id: int | None) -> None:
    client = db.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")

    if encounter_id is not None:
        encounter = db.get(Encounter, encounter_id)
        if encounter is None or encounter.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Обращение не найдено")
        if encounter.client_id != client_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Осмотр нельзя привязать к чужому обращению",
            )


def apply_completion_state(exam: DoctorExam) -> None:
    if exam.is_completed and exam.completed_at is None:
        exam.completed_at = datetime.utcnow()
    if not exam.is_completed:
        exam.completed_at = None


def restore_doctor_role_on_encounter(db: Session, encounter_id: int | None, doctor_role_id: str) -> None:
    if encounter_id is None:
        return
    encounter = db.get(Encounter, encounter_id)
    if encounter is None:
        return

    role_id = str(doctor_role_id or "").strip()
    encounter.suppressed_doctor_role_ids = [
        str(value).strip()
        for value in (encounter.suppressed_doctor_role_ids or [])
        if str(value).strip() and str(value).strip() != role_id
    ]


def suppress_doctor_role_on_encounter(db: Session, encounter_id: int | None, doctor_role_id: str) -> None:
    if encounter_id is None:
        return
    encounter = db.get(Encounter, encounter_id)
    if encounter is None:
        return

    role_id = str(doctor_role_id or "").strip()
    if not role_id:
        return
    suppressed = {
        str(value).strip()
        for value in (encounter.suppressed_doctor_role_ids or [])
        if str(value).strip()
    }
    suppressed.add(role_id)
    encounter.suppressed_doctor_role_ids = sorted(suppressed)


@router.get("", response_model=list[DoctorExamRead])
def list_doctor_exams(
    client_id: int | None = Query(default=None),
    client_ids: list[int] | None = Query(default=None),
    encounter_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[DoctorExamRead]:
    query = select(DoctorExam).where(DoctorExam.deleted_at.is_(None)).order_by(DoctorExam.id.desc())
    if client_id is not None:
        query = query.where(DoctorExam.client_id == client_id)
    if client_ids:
        query = query.where(DoctorExam.client_id.in_(client_ids))
    if encounter_id is not None:
        query = query.where(DoctorExam.encounter_id == encounter_id)
    exams = db.execute(query).scalars().all()
    return [DoctorExamRead.model_validate(item) for item in exams]


@router.post("", response_model=DoctorExamRead)
def create_or_update_doctor_exam(payload: DoctorExamCreate, db: Session = Depends(get_db)) -> DoctorExamRead:
    validate_links(db, payload.client_id, payload.encounter_id)

    query = select(DoctorExam).where(
        DoctorExam.deleted_at.is_(None),
        DoctorExam.client_id == payload.client_id,
        DoctorExam.doctor_role_id == payload.doctor_role_id,
    )
    if payload.encounter_id is None:
        query = query.where(DoctorExam.encounter_id.is_(None))
    else:
        query = query.where(DoctorExam.encounter_id == payload.encounter_id)

    exam = db.execute(query).scalars().first()
    action = "update"
    if exam is None:
        exam = DoctorExam(created_by_user_id=1, **payload.model_dump())
        db.add(exam)
        action = "create"
    else:
        for key, value in payload.model_dump().items():
            setattr(exam, key, value)

    restore_doctor_role_on_encounter(db, exam.encounter_id, exam.doctor_role_id)
    apply_completion_state(exam)
    db.commit()
    db.refresh(exam)
    write_audit_log(
        db,
        entity_type="doctor_exam",
        entity_id=exam.id,
        action=action,
        user_id=1,
        payload_json={"client_id": exam.client_id, "doctor_role_id": exam.doctor_role_id},
    )
    db.commit()
    return DoctorExamRead.model_validate(exam)


@router.put("/{exam_id}", response_model=DoctorExamRead)
def update_doctor_exam(exam_id: int, payload: DoctorExamUpdate, db: Session = Depends(get_db)) -> DoctorExamRead:
    exam = db.get(DoctorExam, exam_id)
    if exam is None or exam.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Осмотр не найден")

    next_encounter_id = payload.encounter_id if "encounter_id" in payload.model_fields_set else exam.encounter_id
    validate_links(db, exam.client_id, next_encounter_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(exam, key, value)

    apply_completion_state(exam)
    db.commit()
    db.refresh(exam)
    write_audit_log(
        db,
        entity_type="doctor_exam",
        entity_id=exam.id,
        action="update",
        user_id=1,
        payload_json={"client_id": exam.client_id, "doctor_role_id": exam.doctor_role_id},
    )
    db.commit()
    return DoctorExamRead.model_validate(exam)


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doctor_exam(exam_id: int, db: Session = Depends(get_db)) -> None:
    exam = db.get(DoctorExam, exam_id)
    if exam is None or exam.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Осмотр не найден")

    exam.deleted_at = datetime.utcnow()
    suppress_doctor_role_on_encounter(db, exam.encounter_id, exam.doctor_role_id)
    db.commit()
    write_audit_log(
        db,
        entity_type="doctor_exam",
        entity_id=exam.id,
        action="delete",
        user_id=1,
        payload_json={"client_id": exam.client_id, "doctor_role_id": exam.doctor_role_id},
    )
    db.commit()
