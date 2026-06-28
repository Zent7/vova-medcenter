from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.doctor_exam import DoctorExam
from app.models.encounter import Encounter
from app.models.medical_record import MedicalRecord, MedicalRecordEntry
from app.models.service import DoctorRole, ServiceDoctorRole
from app.models.template_phrase import TemplatePhrase


NO_COMPLAINTS_TEXT = "в момент осмотра жалоб нет"
DEFAULT_NORMAL_TEXT = "Противопоказаний не выявлено"
CHAIRMAN_ROLE_CODE = "chairman"


def _first_text(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _apply_if_empty(target: object, field_name: str, value: object) -> None:
    if _first_text(getattr(target, field_name, None)):
        return
    setattr(target, field_name, value)


def _default_phrase_for_role(db: Session, role: DoctorRole, service_id: int) -> str:
    phrase = db.execute(
        select(TemplatePhrase)
        .where(
            TemplatePhrase.is_active.is_(True),
            TemplatePhrase.doctor_role_id == role.id,
            TemplatePhrase.code == "normal",
            (TemplatePhrase.service_id == service_id) | (TemplatePhrase.service_id.is_(None)),
        )
        .order_by(TemplatePhrase.service_id.is_(None).asc(), TemplatePhrase.is_default.desc(), TemplatePhrase.id.asc())
    ).scalars().first()
    return _first_text(phrase.text if phrase else None, DEFAULT_NORMAL_TEXT)


def _ensure_medical_record(db: Session, encounter: Encounter) -> MedicalRecord:
    record = db.execute(
        select(MedicalRecord).where(
            MedicalRecord.client_id == encounter.client_id,
            MedicalRecord.deleted_at.is_(None),
        )
    ).scalars().first()
    if record is not None:
        _apply_if_empty(record, "center_id", encounter.center_id)
        _apply_if_empty(record, "opened_at", encounter.encounter_date)
        return record

    record = MedicalRecord(
        client_id=encounter.client_id,
        center_id=encounter.center_id,
        opened_at=encounter.encounter_date,
    )
    db.add(record)
    db.flush()
    return record


def _ensure_completed_exam(
    db: Session,
    encounter: Encounter,
    role: DoctorRole,
    phrase_text: str,
) -> DoctorExam:
    exam = db.execute(
        select(DoctorExam).where(
            DoctorExam.deleted_at.is_(None),
            DoctorExam.client_id == encounter.client_id,
            DoctorExam.encounter_id == encounter.id,
            DoctorExam.doctor_role_id == role.code,
        )
    ).scalars().first()
    if exam is None:
        exam = DoctorExam(
            client_id=encounter.client_id,
            encounter_id=encounter.id,
            doctor_role_id=role.code,
            doctor_name=role.name,
            result_text=phrase_text,
            diagnosis=phrase_text,
            fields_json={
                "complaints": NO_COMPLAINTS_TEXT,
                "complaintsPreset": "Норма",
                "diagnosis": phrase_text,
                "conclusion": phrase_text,
            },
            is_completed=True,
            completed_at=datetime.utcnow(),
            created_by_user_id=1,
        )
        db.add(exam)
        db.flush()
        return exam

    _apply_if_empty(exam, "doctor_name", role.name)
    _apply_if_empty(exam, "result_text", phrase_text)
    _apply_if_empty(exam, "diagnosis", phrase_text)

    fields = dict(exam.fields_json or {})
    fields.setdefault("complaints", NO_COMPLAINTS_TEXT)
    fields.setdefault("complaintsPreset", "Норма")
    fields.setdefault("diagnosis", phrase_text)
    fields.setdefault("conclusion", phrase_text)
    exam.fields_json = fields

    if not exam.is_completed:
        exam.is_completed = True
        exam.completed_at = datetime.utcnow()
    elif exam.completed_at is None:
        exam.completed_at = datetime.utcnow()
    return exam


def _ensure_medical_record_entry(
    db: Session,
    encounter: Encounter,
    record: MedicalRecord,
    exam: DoctorExam,
    role: DoctorRole,
    phrase_text: str,
) -> None:
    entry = db.execute(
        select(MedicalRecordEntry).where(
            MedicalRecordEntry.medical_record_id == record.id,
            MedicalRecordEntry.encounter_id == encounter.id,
            MedicalRecordEntry.doctor_role_id == role.code,
        )
    ).scalars().first()
    if entry is None:
        db.add(
            MedicalRecordEntry(
                medical_record_id=record.id,
                encounter_id=encounter.id,
                doctor_exam_id=exam.id,
                entry_date=encounter.encounter_date,
                doctor_role_id=role.code,
                doctor_name=exam.doctor_name or role.name,
                complaints=NO_COMPLAINTS_TEXT,
                objective_data=phrase_text,
                diagnosis=phrase_text,
                conclusion=phrase_text,
            )
        )
        return

    _apply_if_empty(entry, "doctor_exam_id", exam.id)
    _apply_if_empty(entry, "entry_date", encounter.encounter_date)
    _apply_if_empty(entry, "doctor_name", exam.doctor_name or role.name)
    _apply_if_empty(entry, "complaints", NO_COMPLAINTS_TEXT)
    _apply_if_empty(entry, "objective_data", phrase_text)
    _apply_if_empty(entry, "diagnosis", phrase_text)
    _apply_if_empty(entry, "conclusion", phrase_text)


def autofill_completed_doctors_for_service(db: Session, encounter: Encounter, service_id: int) -> None:
    roles = db.execute(
        select(DoctorRole)
        .join(ServiceDoctorRole, ServiceDoctorRole.doctor_role_id == DoctorRole.id)
        .where(
            ServiceDoctorRole.service_id == service_id,
            DoctorRole.is_active.is_(True),
            DoctorRole.code != CHAIRMAN_ROLE_CODE,
        )
        .order_by(DoctorRole.sort_order.asc(), DoctorRole.name.asc())
    ).scalars().all()
    if not roles:
        return

    record = _ensure_medical_record(db, encounter)
    for role in roles:
        phrase_text = _default_phrase_for_role(db, role, service_id)
        exam = _ensure_completed_exam(db, encounter, role, phrase_text)
        _ensure_medical_record_entry(db, encounter, record, exam, role, phrase_text)
