from collections import defaultdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, false, func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.routes.clients import client_search_conditions
from app.db.session import get_db
from app.models.client import Client
from app.models.center import Center
from app.models.doctor_exam import DoctorExam
from app.models.encounter import Encounter
from app.models.encounter_service import EncounterService
from app.models.generated_document import GeneratedDocument
from app.models.recall import Recall
from app.models.service import Service
from app.schemas.dashboard import (
    DashboardClientDoctorStatus,
    DashboardClientDoctorStatusService,
    DashboardEncounterRow,
    DashboardStats,
)

router = APIRouter()


def _append_unique_role(target: list[str], role_id: object) -> None:
    normalized = str(role_id or "").strip()
    if normalized and normalized not in target:
        target.append(normalized)


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


@router.get("/encounter-rows", response_model=list[DashboardEncounterRow])
def get_dashboard_encounter_rows(
    search: Annotated[str | None, Query()] = None,
    encounter_date: Annotated[date | None, Query()] = None,
    encounter_date_from: Annotated[date | None, Query()] = None,
    encounter_date_to: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> list[DashboardEncounterRow]:
    """Return the dashboard journal with one row per active encounter.

    Clients without an active encounter are kept as a single empty journal
    row when no encounter-date filter is active.  Services are loaded for the
    row's exact encounter, so an older multi-service encounter remains one
    row and never inherits services from a newer encounter.
    """

    active_encounter_join = and_(
        Encounter.client_id == Client.id,
        Encounter.deleted_at.is_(None),
    )
    query = (
        select(Client, Encounter)
        .outerjoin(Encounter, active_encounter_join)
        .where(Client.deleted_at.is_(None))
    )

    search_value = (search or "").strip()
    if search_value:
        search_conditions = client_search_conditions(search_value)
        query = query.where(or_(*search_conditions) if search_conditions else false())

    range_from = encounter_date_from or encounter_date
    range_to = encounter_date_to or encounter_date
    if range_from is not None:
        query = query.where(Encounter.encounter_date >= range_from)
    if range_to is not None:
        query = query.where(Encounter.encounter_date <= range_to)

    query = query.order_by(
        case((Encounter.id.is_(None), 1), else_=0).asc(),
        Encounter.created_at.desc(),
        Encounter.id.desc(),
        Client.created_at.desc(),
        Client.id.desc(),
    ).offset(offset).limit(limit)

    journal_rows = db.execute(query).all()
    encounter_ids = [encounter.id for _, encounter in journal_rows if encounter is not None]
    center_ids = list({encounter.center_id for _, encounter in journal_rows if encounter is not None})
    centers_by_id = (
        dict(db.execute(select(Center.id, Center.name).where(Center.id.in_(center_ids))).all())
        if center_ids
        else {}
    )
    services_by_encounter: dict[int, list[str]] = defaultdict(list)
    if encounter_ids:
        service_rows = db.execute(
            select(EncounterService.encounter_id, Service.name)
            .join(Service, Service.id == EncounterService.service_id)
            .where(EncounterService.encounter_id.in_(encounter_ids))
            .order_by(EncounterService.encounter_id.asc(), EncounterService.id.asc())
        ).all()
        for row_encounter_id, service_name in service_rows:
            if service_name:
                services_by_encounter[row_encounter_id].append(service_name)

    result: list[DashboardEncounterRow] = []
    for client, encounter in journal_rows:
        encounter_created_at = encounter.created_at if encounter is not None else None
        result.append(
            DashboardEncounterRow(
                id=client.id,
                client_id=client.id,
                patient_number=client.patient_number,
                created_at=client.created_at,
                last_name=client.last_name,
                first_name=client.first_name,
                middle_name=client.middle_name,
                birth_date=client.birth_date,
                sex=client.sex,
                phone=client.phone,
                document_type=client.document_type,
                document_series=client.document_series,
                document_number=client.document_number,
                snils=client.snils,
                address_text=client.address_text,
                registration_text=client.registration_text,
                admission_category=client.admission_category,
                reference_number=client.reference_number,
                notes=client.notes,
                encounter_date_text=client.encounter_date_text,
                card_number=client.card_number,
                profession=client.profession,
                work_place=client.work_place,
                organization=client.organization,
                real_date_text=client.real_date_text,
                encounter_id=encounter.id if encounter is not None else None,
                encounter_date=encounter.encounter_date if encounter is not None else None,
                encounter_created_at=encounter_created_at,
                latest_encounter_created_at=encounter_created_at,
                encounter_status=encounter.status if encounter is not None else None,
                center_id=encounter.center_id if encounter is not None else None,
                center_name=centers_by_id.get(encounter.center_id) if encounter is not None else None,
                payment_type=encounter.payment_type if encounter is not None else None,
                total_amount=encounter.total_amount if encounter is not None else None,
                comment=encounter.comment if encounter is not None else None,
                services=services_by_encounter[encounter.id] if encounter is not None else [],
            )
        )
    return result


@router.get("/client-doctor-statuses", response_model=list[DashboardClientDoctorStatus])
def get_client_doctor_statuses(
    client_ids: Annotated[list[int], Query()],
    encounter_ids: Annotated[list[int] | None, Query()] = None,
    db: Session = Depends(get_db),
) -> list[DashboardClientDoctorStatus]:
    unique_client_ids = list(dict.fromkeys(client_ids))
    unique_encounter_ids = list(dict.fromkeys(encounter_ids or []))
    if not unique_client_ids and not unique_encounter_ids:
        return []

    encounter_query = select(
        Encounter.id,
        Encounter.client_id,
        Encounter.status,
        Encounter.suppressed_doctor_role_ids,
    ).where(Encounter.deleted_at.is_(None))
    if unique_encounter_ids:
        encounter_query = encounter_query.where(Encounter.id.in_(unique_encounter_ids))
        if unique_client_ids:
            encounter_query = encounter_query.where(Encounter.client_id.in_(unique_client_ids))
    else:
        encounter_query = encounter_query.where(Encounter.client_id.in_(unique_client_ids)).order_by(
            Encounter.client_id.asc(),
            Encounter.created_at.desc(),
            Encounter.id.desc(),
        )

    encounter_rows = db.execute(encounter_query).all()
    encounter_by_id: dict[int, tuple[int, str, list[str]]] = {}
    latest_encounter_by_client: dict[int, tuple[int, str, list[str]]] = {}
    for row_encounter_id, client_id, encounter_status, suppressed_doctor_role_ids in encounter_rows:
        encounter_data = (
            client_id,
            encounter_status,
            suppressed_doctor_role_ids if isinstance(suppressed_doctor_role_ids, list) else [],
        )
        encounter_by_id[row_encounter_id] = encounter_data
        latest_encounter_by_client.setdefault(
            client_id,
            (row_encounter_id, encounter_status, encounter_data[2]),
        )

    selected_encounter_ids = (
        [encounter_id for encounter_id in unique_encounter_ids if encounter_id in encounter_by_id]
        if unique_encounter_ids
        else [encounter_id for encounter_id, _, _ in latest_encounter_by_client.values()]
    )
    services_by_encounter: dict[int, list[DashboardClientDoctorStatusService]] = defaultdict(list)
    existing_roles_by_encounter: dict[int, list[str]] = defaultdict(list)
    completed_roles_by_encounter: dict[int, list[str]] = defaultdict(list)
    blank_number_by_encounter: dict[int, str] = {}

    if selected_encounter_ids:
        service_rows = db.execute(
            select(EncounterService.encounter_id, EncounterService.service_id, EncounterService.notes)
            .where(EncounterService.encounter_id.in_(selected_encounter_ids))
            .order_by(EncounterService.encounter_id.asc(), EncounterService.id.asc())
        ).all()
        for encounter_id, service_id, notes in service_rows:
            services_by_encounter[encounter_id].append(
                DashboardClientDoctorStatusService(service_id=service_id, notes=notes)
            )

        exam_rows = db.execute(
            select(DoctorExam.encounter_id, DoctorExam.doctor_role_id, DoctorExam.is_completed)
            .where(
                DoctorExam.deleted_at.is_(None),
                DoctorExam.encounter_id.in_(selected_encounter_ids),
            )
            .order_by(DoctorExam.encounter_id.asc(), DoctorExam.id.asc())
        ).all()
        for encounter_id, doctor_role_id, is_completed in exam_rows:
            _append_unique_role(existing_roles_by_encounter[encounter_id], doctor_role_id)
            if is_completed:
                _append_unique_role(completed_roles_by_encounter[encounter_id], doctor_role_id)

        blank_rows = db.execute(
            select(GeneratedDocument.encounter_id, GeneratedDocument.blank_number_snapshot)
            .where(
                GeneratedDocument.encounter_id.in_(selected_encounter_ids),
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

    if unique_encounter_ids:
        return [
            DashboardClientDoctorStatus(
                client_id=encounter_by_id[row_encounter_id][0],
                encounter_id=row_encounter_id,
                encounter_status=encounter_by_id[row_encounter_id][1],
                blank_number=blank_number_by_encounter.get(row_encounter_id),
                services=services_by_encounter[row_encounter_id],
                existing_doctor_role_ids=existing_roles_by_encounter[row_encounter_id],
                completed_doctor_role_ids=completed_roles_by_encounter[row_encounter_id],
                suppressed_doctor_role_ids=encounter_by_id[row_encounter_id][2],
            )
            for row_encounter_id in selected_encounter_ids
        ]

    result: list[DashboardClientDoctorStatus] = []
    for client_id in unique_client_ids:
        encounter = latest_encounter_by_client.get(client_id)
        if encounter is None:
            result.append(DashboardClientDoctorStatus(client_id=client_id))
            continue

        encounter_id, encounter_status, suppressed_doctor_role_ids = encounter
        result.append(
            DashboardClientDoctorStatus(
                client_id=client_id,
                encounter_id=encounter_id,
                encounter_status=encounter_status,
                blank_number=blank_number_by_encounter.get(encounter_id),
                services=services_by_encounter[encounter_id],
                existing_doctor_role_ids=existing_roles_by_encounter[encounter_id],
                completed_doctor_role_ids=completed_roles_by_encounter[encounter_id],
                suppressed_doctor_role_ids=suppressed_doctor_role_ids,
            )
        )
    return result
