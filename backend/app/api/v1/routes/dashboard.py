from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.client import Client
from app.models.doctor_exam import DoctorExam
from app.models.encounter import Encounter
from app.models.encounter_service import EncounterService
from app.models.generated_document import GeneratedDocument
from app.models.recall import Recall
from app.models.service import Service
from app.schemas.dashboard import (
    DashboardClientDoctorStatus,
    DashboardClientDoctorStatusService,
    DashboardStats,
)

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)) -> DashboardStats:
    clients_count = db.scalar(select(func.count()).select_from(Client)) or 0
    encounters_count = db.scalar(select(func.count()).select_from(Encounter)) or 0
    services_count = db.scalar(select(func.count()).select_from(Service)) or 0
    recalls_due_count = (
        db.scalar(select(func.count()).select_from(Recall).where(Recall.planned_date <= date.today())) or 0
    )
    return DashboardStats(
        clients_count=clients_count,
        encounters_count=encounters_count,
        services_count=services_count,
        recalls_due_count=recalls_due_count,
    )


@router.get("/client-doctor-statuses", response_model=list[DashboardClientDoctorStatus])
def get_client_doctor_statuses(
    client_ids: list[int] = Query(...),
    db: Session = Depends(get_db),
) -> list[DashboardClientDoctorStatus]:
    unique_client_ids = list(dict.fromkeys(client_ids))
    if not unique_client_ids:
        return []

    encounter_rows = db.execute(
        select(Encounter.id, Encounter.client_id, Encounter.status)
        .where(Encounter.deleted_at.is_(None), Encounter.client_id.in_(unique_client_ids))
        .order_by(Encounter.client_id.asc(), Encounter.created_at.desc(), Encounter.id.desc())
    ).all()

    latest_encounter_by_client: dict[int, tuple[int, str]] = {}
    for encounter_id, client_id, encounter_status in encounter_rows:
        latest_encounter_by_client.setdefault(client_id, (encounter_id, encounter_status))

    encounter_ids = [encounter_id for encounter_id, _ in latest_encounter_by_client.values()]
    services_by_encounter: dict[int, list[DashboardClientDoctorStatusService]] = defaultdict(list)
    completed_roles_by_encounter: dict[int, list[str]] = defaultdict(list)
    blank_number_by_encounter: dict[int, str] = {}

    if encounter_ids:
        service_rows = db.execute(
            select(EncounterService.encounter_id, EncounterService.service_id, EncounterService.notes)
            .where(EncounterService.encounter_id.in_(encounter_ids))
            .order_by(EncounterService.encounter_id.asc(), EncounterService.id.asc())
        ).all()
        for encounter_id, service_id, notes in service_rows:
            services_by_encounter[encounter_id].append(
                DashboardClientDoctorStatusService(service_id=service_id, notes=notes)
            )

        exam_rows = db.execute(
            select(DoctorExam.encounter_id, DoctorExam.doctor_role_id)
            .where(
                DoctorExam.deleted_at.is_(None),
                DoctorExam.is_completed.is_(True),
                DoctorExam.encounter_id.in_(encounter_ids),
            )
            .order_by(DoctorExam.encounter_id.asc(), DoctorExam.id.asc())
        ).all()
        for encounter_id, doctor_role_id in exam_rows:
            if doctor_role_id not in completed_roles_by_encounter[encounter_id]:
                completed_roles_by_encounter[encounter_id].append(doctor_role_id)

        blank_rows = db.execute(
            select(GeneratedDocument.encounter_id, GeneratedDocument.blank_number_snapshot)
            .where(
                GeneratedDocument.encounter_id.in_(encounter_ids),
                GeneratedDocument.blank_number_snapshot.is_not(None),
                GeneratedDocument.cancelled_at.is_(None),
            )
            .order_by(
                GeneratedDocument.encounter_id.asc(),
                GeneratedDocument.generated_at.desc(),
                GeneratedDocument.id.desc(),
            )
        ).all()
        for encounter_id, blank_number in blank_rows:
            if encounter_id is not None and blank_number:
                blank_number_by_encounter.setdefault(encounter_id, blank_number)

    result: list[DashboardClientDoctorStatus] = []
    for client_id in unique_client_ids:
        encounter = latest_encounter_by_client.get(client_id)
        if encounter is None:
            result.append(DashboardClientDoctorStatus(client_id=client_id))
            continue

        encounter_id, encounter_status = encounter
        result.append(
            DashboardClientDoctorStatus(
                client_id=client_id,
                encounter_id=encounter_id,
                encounter_status=encounter_status,
                blank_number=blank_number_by_encounter.get(encounter_id),
                services=services_by_encounter[encounter_id],
                completed_doctor_role_ids=completed_roles_by_encounter[encounter_id],
            )
        )
    return result
