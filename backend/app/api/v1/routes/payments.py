from collections import defaultdict
from datetime import date
from decimal import Decimal
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.center import Center
from app.models.client import Client
from app.models.encounter import Encounter
from app.models.encounter_service import EncounterService
from app.models.payment import Payment
from app.models.service import Service
from app.schemas.payment import CashReportRowRead, CashReportServiceRead, PaymentRead

router = APIRouter()


def _client_full_name(client: Client) -> str:
    parts = [client.last_name, client.first_name, client.middle_name]
    return " ".join(part for part in parts if part).strip()


def _service_comment(notes: str | None) -> str | None:
    if not notes:
        return None
    try:
        value = json.loads(notes)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    comment = value.get("comment")
    return str(comment).strip() if comment else None


def list_cash_report_rows(
    *,
    date_from: date,
    date_to: date,
    center_id: int | None,
    db: Session,
) -> list[CashReportRowRead]:
    query = (
        select(Payment, Encounter, Client, Center)
        .join(Encounter, Encounter.id == Payment.encounter_id)
        .join(Client, Client.id == Encounter.client_id)
        .join(Center, Center.id == Encounter.center_id)
        .where(
            Encounter.deleted_at.is_(None),
            Client.deleted_at.is_(None),
            Payment.status == "paid",
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to,
        )
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
    )
    if center_id is not None:
        query = query.where(Encounter.center_id == center_id)

    payment_rows = db.execute(query).all()
    encounter_ids = [encounter.id for _, encounter, _, _ in payment_rows]
    services_by_encounter: dict[int, list[CashReportServiceRead]] = defaultdict(list)
    if encounter_ids:
        service_rows = db.execute(
            select(EncounterService, Service)
            .join(Service, Service.id == EncounterService.service_id)
            .where(EncounterService.encounter_id.in_(encounter_ids))
            .order_by(EncounterService.encounter_id.asc(), EncounterService.id.asc())
        ).all()
        for encounter_service, service in service_rows:
            quantity = int(encounter_service.quantity or 1)
            base_price = Decimal(service.price or 0) * quantity
            paid_price = Decimal(encounter_service.line_total or 0)
            services_by_encounter[encounter_service.encounter_id].append(
                CashReportServiceRead(
                    service_id=service.id,
                    name=service.name,
                    quantity=quantity,
                    base_price=base_price,
                    paid_price=paid_price,
                    discount=max(Decimal("0.00"), base_price - paid_price),
                    comment=_service_comment(encounter_service.notes),
                )
            )

    result: list[CashReportRowRead] = []
    for payment, encounter, client, center in payment_rows:
        services = services_by_encounter.get(encounter.id, [])
        discount = sum((service.discount for service in services), Decimal("0.00"))
        result.append(
            CashReportRowRead(
                payment_id=payment.id,
                encounter_id=encounter.id,
                client_id=client.id,
                patient_number=client.patient_number,
                client_full_name=_client_full_name(client),
                encounter_date=encounter.encounter_date,
                encounter_created_at=encounter.created_at,
                payment_date=payment.payment_date,
                payment_type=payment.payment_type,
                amount=payment.amount,
                discount=discount,
                comment=payment.comment or encounter.comment,
                center_id=center.id,
                center_name=center.name,
                services=services,
            )
        )
    return result


@router.get("/cash-report", response_model=list[CashReportRowRead])
def get_cash_report(
    date_from: date = Query(...),
    date_to: date = Query(...),
    center_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[CashReportRowRead]:
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return list_cash_report_rows(date_from=date_from, date_to=date_to, center_id=center_id, db=db)


@router.get("", response_model=list[PaymentRead])
def list_payments(
    encounter_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[PaymentRead]:
    query = select(Payment).order_by(Payment.payment_date.desc(), Payment.id.desc())
    if encounter_id is not None:
        query = query.where(Payment.encounter_id == encounter_id)
    items = db.execute(query).scalars().all()
    return [PaymentRead.model_validate(item) for item in items]
