from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select, true
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.client import Client
from app.models.encounter import Encounter
from app.models.encounter_service import EncounterService
from app.models.recall import Recall
from app.models.service import Service, ServiceCategory
from app.schemas.recall import RecallDueRead, RecallMark, RecallRead

router = APIRouter()


@router.get("", response_model=list[RecallRead])
def list_recalls(db: Session = Depends(get_db)) -> list[RecallRead]:
    recalls = db.execute(select(Recall).order_by(Recall.planned_date.asc())).scalars().all()
    return [RecallRead.model_validate(item) for item in recalls]


@router.get("/due", response_model=list[RecallDueRead])
def list_due_recalls(
    horizon_days: int = Query(default=45, ge=0, le=3650),
    include_done: bool = Query(default=False),
    center_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[RecallDueRead]:
    """Повторы к обзвону. С `center_id` — только по обращениям этого медцентра.

    Без фильтра регистратор третьего медцентра видел бы пациентов первого и
    звал бы на повтор в чужой центр.
    """

    today = date.today()
    horizon = today + timedelta(days=horizon_days)
    seen_keys: set[tuple[int, int, int]] = set()

    rows = db.execute(
        select(Client, Encounter, EncounterService, Service, ServiceCategory, Recall)
        .join(Encounter, Encounter.client_id == Client.id)
        .join(EncounterService, EncounterService.encounter_id == Encounter.id)
        .join(Service, Service.id == EncounterService.service_id)
        .outerjoin(ServiceCategory, ServiceCategory.id == Service.category_id)
        .outerjoin(
            Recall,
            and_(
                Recall.client_id == Client.id,
                Recall.encounter_id == Encounter.id,
                Recall.service_id == Service.id,
            ),
        )
        .where(Client.deleted_at.is_(None))
        .where(Encounter.deleted_at.is_(None))
        .where(Service.recall_after_days.is_not(None))
        .where(Encounter.center_id == center_id if center_id is not None else true())
        .order_by(Encounter.encounter_date.asc(), Client.last_name.asc(), Client.first_name.asc())
    ).all()

    result: list[RecallDueRead] = []
    for client, encounter, _encounter_service, service, service_category, recall in rows:
        key = (client.id, encounter.id, service.id)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        recall_after_days = int(service.recall_after_days or 0)
        if recall_after_days <= 0:
            continue

        planned_date = recall.planned_date if recall else encounter.encounter_date + timedelta(days=recall_after_days)
        if planned_date > horizon:
            continue

        status = recall.status if recall else "planned"
        if not include_done and status in {"called", "skipped"}:
            continue

        full_name = " ".join(
            part for part in [client.last_name, client.first_name, client.middle_name] if part
        ).strip() or f"Клиент {client.patient_number or client.id}"

        result.append(
            RecallDueRead(
                client_id=client.id,
                patient_number=client.patient_number,
                full_name=full_name,
                phone=client.phone,
                encounter_id=encounter.id,
                encounter_date=encounter.encounter_date,
                service_id=service.id,
                service_name=service.name,
                service_category_id=service.category_id,
                service_category_name=service_category.name if service_category else None,
                recall_after_days=recall_after_days,
                planned_date=planned_date,
                days_left=(planned_date - today).days,
                status=status,
                comment=recall.comment if recall else None,
                recall_id=recall.id if recall else None,
            )
        )

    result.sort(key=lambda item: (item.planned_date, item.full_name, item.service_name))
    return result


@router.post("/mark", response_model=RecallRead)
def mark_recall(payload: RecallMark, db: Session = Depends(get_db)) -> RecallRead:
    recall = db.execute(
        select(Recall).where(
            Recall.client_id == payload.client_id,
            Recall.encounter_id == payload.encounter_id,
            Recall.service_id == payload.service_id,
        )
    ).scalar_one_or_none()

    if recall is None:
        recall = Recall(
            client_id=payload.client_id,
            encounter_id=payload.encounter_id,
            service_id=payload.service_id,
            planned_date=payload.planned_date,
        )
        db.add(recall)

    recall.status = payload.status
    recall.comment = payload.comment
    recall.planned_date = payload.planned_date

    db.commit()
    db.refresh(recall)
    return RecallRead.model_validate(recall)
