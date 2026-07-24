from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import get_optional_current_user
from app.db.session import get_db
from app.models.center import Center
from app.models.client import Client
from app.models.encounter import Encounter
from app.models.encounter_service import EncounterService
from app.models.payment import Payment
from app.models.service import Service
from app.models.user import User
from app.schemas.encounter import (
    DeletedEncounterRead,
    EncounterByServiceRead,
    EncounterCreate,
    EncounterRead,
    EncountersByServicesCreate,
    EncounterUpdate,
)
from app.schemas.encounter_service import EncounterServiceRead
from app.schemas.payment import PaymentRead
from app.services.audit import write_audit_log
from app.services.medical_autofill import autofill_completed_doctors_for_service
from app.services.notifications import build_deletion_email_body, send_deletion_notification
from app.services.system_user import get_system_user_id

router = APIRouter()


def actor_user_id(db: Session, current_user: User | None) -> int | None:
    return current_user.id if current_user is not None else get_system_user_id(db)


def sync_primary_payment(
    db: Session,
    encounter: Encounter,
    *,
    default_comment: str = "Первичный платёж",
) -> Payment:
    payment = db.execute(
        select(Payment).where(Payment.encounter_id == encounter.id).order_by(Payment.id.asc()).limit(1)
    ).scalar_one_or_none()
    if payment is None:
        payment = Payment(
            encounter_id=encounter.id,
            created_by_user_id=encounter.created_by_user_id,
        )
        db.add(payment)

    payment.payment_date = encounter.encounter_date
    payment.payment_type = encounter.payment_type
    payment.amount = encounter.total_amount
    payment.status = "paid"
    payment.comment = encounter.comment or default_comment
    return payment


@router.get("", response_model=list[EncounterRead])
def list_encounters(
    client_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[EncounterRead]:
    query = select(Encounter).where(Encounter.deleted_at.is_(None))
    if client_id is not None:
        query = query.where(Encounter.client_id == client_id)
    query = query.order_by(Encounter.created_at.desc())
    encounters = db.execute(query).scalars().all()
    return [EncounterRead.model_validate(item) for item in encounters]


@router.get("/deleted", response_model=list[DeletedEncounterRead])
def list_deleted_encounters(
    client_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[DeletedEncounterRead]:
    query = select(Encounter).where(Encounter.deleted_at.is_not(None))
    if client_id is not None:
        query = query.where(Encounter.client_id == client_id)
    query = query.order_by(Encounter.deleted_at.desc()).limit(limit)
    encounters = db.execute(query).scalars().all()
    return [
        DeletedEncounterRead(
            id=encounter.id,
            center_id=encounter.center_id,
            client_id=encounter.client_id,
            encounter_date=encounter.encounter_date,
            payment_type=encounter.payment_type,
            total_amount=encounter.total_amount,
            status=encounter.status,
            deleted_at=encounter.deleted_at,
        )
        for encounter in encounters
        if encounter.deleted_at is not None
    ]


@router.post(
    "/by-services",
    response_model=list[EncounterByServiceRead],
    status_code=status.HTTP_201_CREATED,
)
def create_encounters_by_services(
    payload: EncountersByServicesCreate,
    db: Session = Depends(get_db),
) -> list[EncounterByServiceRead]:
    client = db.get(Client, payload.client_id)
    if client is None or client.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")

    center = db.get(Center, payload.center_id)
    if center is None or not center.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Медцентр не найден")

    requested_service_ids = list(dict.fromkeys(item.service_id for item in payload.services))
    services = db.execute(select(Service).where(Service.id.in_(requested_service_ids))).scalars().all()
    service_by_id = {service.id: service for service in services}
    invalid_service_ids = [
        service_id
        for service_id in requested_service_ids
        if service_id not in service_by_id or not service_by_id[service_id].is_active
    ]
    if invalid_service_ids:
        invalid_ids = ", ".join(str(service_id) for service_id in invalid_service_ids)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Услуги не найдены или неактивны: {invalid_ids}",
        )

    created_by_user_id = get_system_user_id(db)
    created_items: list[tuple[Encounter, EncounterService, Payment]] = []
    try:
        for service_item in payload.services:
            service = service_by_id[service_item.service_id]
            unit_price = service_item.unit_price if service_item.unit_price is not None else service.price
            encounter = Encounter(
                center_id=payload.center_id,
                client_id=payload.client_id,
                visit_type_id=payload.visit_type_id,
                created_by_user_id=created_by_user_id,
                encounter_date=payload.encounter_date,
                payment_type=service_item.payment_type,
                total_amount=unit_price,
                comment=service_item.comment,
                status="draft",
            )
            db.add(encounter)
            db.flush()

            payment = sync_primary_payment(db, encounter)
            sequence_number = service_item.sequence_number
            if service.requires_sequence and not sequence_number:
                service_count = db.scalar(
                    select(func.count(EncounterService.id)).where(EncounterService.service_id == service.id)
                ) or 0
                sequence_number = str(service_count + 1)

            encounter_service = EncounterService(
                encounter_id=encounter.id,
                service_id=service.id,
                quantity=1,
                unit_price=unit_price,
                line_total=unit_price,
                sequence_number=sequence_number,
                notes=service_item.notes,
            )
            db.add(encounter_service)
            db.flush()
            autofill_completed_doctors_for_service(db, encounter, service.id)
            write_audit_log(
                db,
                entity_type="encounter",
                entity_id=encounter.id,
                action="create",
                user_id=created_by_user_id,
                center_id=encounter.center_id,
                payload_json={"client_id": encounter.client_id, "service_id": service.id},
            )
            created_items.append((encounter, encounter_service, payment))

        db.commit()
    except Exception:
        db.rollback()
        raise

    result: list[EncounterByServiceRead] = []
    for encounter, encounter_service, payment in created_items:
        db.refresh(encounter)
        db.refresh(encounter_service)
        db.refresh(payment)
        result.append(
            EncounterByServiceRead(
                encounter=EncounterRead.model_validate(encounter),
                service=EncounterServiceRead.model_validate(encounter_service),
                payment=PaymentRead.model_validate(payment),
            )
        )
    return result


@router.get("/{encounter_id}", response_model=EncounterRead)
def get_encounter(encounter_id: int, db: Session = Depends(get_db)) -> EncounterRead:
    encounter = db.get(Encounter, encounter_id)
    if encounter is None or encounter.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Обращение не найдено")
    return EncounterRead.model_validate(encounter)


@router.post("", response_model=EncounterRead)
def create_encounter(payload: EncounterCreate, db: Session = Depends(get_db)) -> EncounterRead:
    client = db.get(Client, payload.client_id)
    if client is None or client.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")

    created_by_user_id = get_system_user_id(db)
    encounter = Encounter(**payload.model_dump(), created_by_user_id=created_by_user_id, status="draft")
    client.encounter_date_text = payload.encounter_date.isoformat()
    db.add(encounter)
    db.flush()
    sync_primary_payment(db, encounter)
    db.commit()
    db.refresh(encounter)
    write_audit_log(
        db,
        entity_type="encounter",
        entity_id=encounter.id,
        action="create",
        user_id=created_by_user_id,
        center_id=encounter.center_id,
        payload_json={"client_id": encounter.client_id},
    )
    db.commit()
    return EncounterRead.model_validate(encounter)


@router.put("/{encounter_id}", response_model=EncounterRead)
def update_encounter(encounter_id: int, payload: EncounterUpdate, db: Session = Depends(get_db)) -> EncounterRead:
    encounter = db.get(Encounter, encounter_id)
    if encounter is None or encounter.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Обращение не найдено")

    encounter_date_before_update = encounter.encounter_date
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(encounter, key, value)

    if payload.encounter_date is not None and payload.encounter_date != encounter_date_before_update:
        client = db.get(Client, encounter.client_id)
        if client is not None and client.deleted_at is None:
            client.encounter_date_text = payload.encounter_date.isoformat()

    sync_primary_payment(db, encounter)
    db.commit()
    db.refresh(encounter)
    write_audit_log(
        db,
        entity_type="encounter",
        entity_id=encounter.id,
        action="update",
        user_id=get_system_user_id(db),
        center_id=encounter.center_id,
        payload_json={"client_id": encounter.client_id, "status": encounter.status},
    )
    db.commit()
    return EncounterRead.model_validate(encounter)


@router.delete("/{encounter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_encounter(
    encounter_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> None:
    encounter = db.get(Encounter, encounter_id)
    if encounter is None or encounter.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Обращение не найдено")

    encounter.deleted_at = datetime.now(timezone.utc)
    deleted_at_iso = encounter.deleted_at.isoformat()
    deleted_by_user_id = actor_user_id(db, current_user)
    db.commit()
    write_audit_log(
        db,
        entity_type="encounter",
        entity_id=encounter.id,
        action="delete",
        user_id=deleted_by_user_id,
        center_id=encounter.center_id,
        payload_json={
            "client_id": encounter.client_id,
            "encounter_date": encounter.encounter_date.isoformat(),
            "deleted_at": deleted_at_iso,
        },
    )
    db.commit()

    try:
        send_deletion_notification(
            subject=f"Удалено обращение №{encounter.id}",
            body=build_deletion_email_body(
                entity_label="обращение",
                entity_id=encounter.id,
                deleted_by=current_user.full_name if current_user is not None else None,
                deleted_at=deleted_at_iso,
                details={
                    "Клиент ID": encounter.client_id,
                    "Дата обращения": encounter.encounter_date.isoformat(),
                    "Статус": encounter.status,
                },
            ),
        )
    except Exception:
        pass


@router.post("/{encounter_id}/restore", response_model=EncounterRead)
def restore_encounter(
    encounter_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> EncounterRead:
    encounter = db.get(Encounter, encounter_id)
    if encounter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Обращение не найдено")
    if encounter.deleted_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Обращение не находится в удалённых")

    encounter.deleted_at = None
    restored_by_user_id = actor_user_id(db, current_user)
    db.commit()
    db.refresh(encounter)
    write_audit_log(
        db,
        entity_type="encounter",
        entity_id=encounter.id,
        action="restore",
        user_id=restored_by_user_id,
        center_id=encounter.center_id,
        payload_json={"client_id": encounter.client_id, "status": encounter.status},
    )
    db.commit()
    return EncounterRead.model_validate(encounter)
