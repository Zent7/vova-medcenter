from collections import defaultdict
from datetime import date, datetime, timezone
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import get_optional_current_user
from app.db.session import get_db
from app.models.client import Client
from app.models.encounter import Encounter
from app.models.encounter_service import EncounterService
from app.models.medical_record import MedicalRecord
from app.models.service import Service
from app.models.user import User
from app.schemas.client import ClientCreate, ClientRead, ClientSearchRead, ClientUpdate, DeletedClientRead
from app.services.audit import write_audit_log
from app.services.duplicates import build_duplicate_check_keys
from app.services.notifications import build_deletion_email_body, send_deletion_notification
from app.services.system_user import get_system_user_id

router = APIRouter()


def normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def capitalize_name_part(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    return re.sub(
        r"[^\s-]+",
        lambda match: match.group(0)[:1].upper() + match.group(0)[1:].lower(),
        normalized,
    )


def normalize_payload(payload: ClientCreate | ClientUpdate) -> dict:
    data = payload.model_dump()
    for key, value in list(data.items()):
        if isinstance(value, str):
            data[key] = normalize_optional(value)
    for key in ("last_name", "first_name", "middle_name"):
        data[key] = capitalize_name_part(data.get(key))
    data["last_name"] = data["last_name"] or ""
    data["first_name"] = data["first_name"] or ""
    return data


def parse_search_date(value: str):
    for date_format in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    short_match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{2})", value)
    if short_match:
        day, month, year = short_match.groups()
        current_year = date.today().year
        current_century = current_year // 100 * 100
        full_year = (current_century if int(year) <= current_year % 100 + 20 else current_century - 100) + int(year)
        try:
            return date(full_year, int(month), int(day))
        except ValueError:
            return None
    return None


def actor_user_id(db: Session, current_user: User | None) -> int | None:
    return current_user.id if current_user is not None else get_system_user_id(db)


def client_full_name(client: Client) -> str:
    return f"{client.last_name} {client.first_name} {client.middle_name or ''}".strip()


def duplicate_conditions_for(payload: ClientCreate | ClientUpdate):
    if not (payload.last_name and payload.first_name and payload.middle_name):
        return []

    return [
        (Client.last_name == payload.last_name)
        & (Client.first_name == payload.first_name)
        & (Client.middle_name == payload.middle_name),
        (func.lower(Client.last_name) == payload.last_name.lower())
        & (func.lower(Client.first_name) == payload.first_name.lower())
        & (func.lower(Client.middle_name) == payload.middle_name.lower())
    ]


def find_duplicate(
    db: Session,
    payload: ClientCreate | ClientUpdate,
    exclude_client_id: int | None = None,
) -> Client | None:
    conditions = duplicate_conditions_for(payload)
    if not conditions:
        return None

    query = select(Client).where(Client.deleted_at.is_(None), or_(*conditions))
    if exclude_client_id is not None:
        query = query.where(Client.id != exclude_client_id)
    return db.execute(query).scalars().first()


def get_next_patient_number(db: Session) -> int:
    patient_numbers = db.execute(select(Client.patient_number).order_by(Client.patient_number.asc())).scalars()
    expected_number = 1
    for patient_number in patient_numbers:
        if patient_number is None or patient_number < expected_number:
            continue
        if patient_number > expected_number:
            break
        expected_number += 1
    return expected_number


def latest_services_by_client_ids(db: Session, client_ids: list[int]) -> dict[int, list[str]]:
    if not client_ids:
        return {}

    encounter_rows = db.execute(
        select(Encounter.id, Encounter.client_id)
        .where(Encounter.deleted_at.is_(None), Encounter.client_id.in_(client_ids))
        .order_by(Encounter.client_id.asc(), Encounter.created_at.desc(), Encounter.id.desc())
    ).all()

    latest_encounter_by_client: dict[int, int] = {}
    for encounter_id, client_id in encounter_rows:
        latest_encounter_by_client.setdefault(client_id, encounter_id)

    if not latest_encounter_by_client:
        return {}

    service_rows = db.execute(
        select(EncounterService.encounter_id, Service.name)
        .join(Service, Service.id == EncounterService.service_id)
        .where(EncounterService.encounter_id.in_(list(latest_encounter_by_client.values())))
        .order_by(EncounterService.encounter_id.asc(), EncounterService.id.asc())
    ).all()

    names_by_encounter: dict[int, list[str]] = defaultdict(list)
    for encounter_id, service_name in service_rows:
        if service_name:
            names_by_encounter[encounter_id].append(service_name)

    return {
        client_id: names_by_encounter.get(encounter_id, [])
        for client_id, encounter_id in latest_encounter_by_client.items()
    }


def latest_encounter_created_at_by_client_ids(db: Session, client_ids: list[int]) -> dict[int, datetime]:
    if not client_ids:
        return {}

    rows = db.execute(
        select(Encounter.client_id, Encounter.created_at)
        .where(Encounter.deleted_at.is_(None), Encounter.client_id.in_(client_ids))
        .order_by(Encounter.client_id.asc(), Encounter.created_at.desc(), Encounter.id.desc())
    ).all()

    result: dict[int, datetime] = {}
    for client_id, created_at in rows:
        result.setdefault(client_id, created_at)
    return result


def serialize_client(db: Session, client: Client) -> ClientRead:
    services = latest_services_by_client_ids(db, [client.id]).get(client.id, [])
    latest_encounter_created_at = latest_encounter_created_at_by_client_ids(db, [client.id]).get(client.id)
    payload = ClientRead.model_validate(client).model_dump()
    payload["services"] = services
    payload["latest_encounter_created_at"] = latest_encounter_created_at
    return ClientRead.model_validate(payload)


def serialize_clients(db: Session, clients: list[Client]) -> list[ClientRead]:
    client_ids = [client.id for client in clients]
    services_by_client = latest_services_by_client_ids(db, client_ids)
    latest_encounter_created_at_by_client = latest_encounter_created_at_by_client_ids(db, client_ids)
    result: list[ClientRead] = []
    for client in clients:
        payload = ClientRead.model_validate(client).model_dump()
        payload["services"] = services_by_client.get(client.id, [])
        payload["latest_encounter_created_at"] = latest_encounter_created_at_by_client.get(client.id)
        result.append(ClientRead.model_validate(payload))
    return result


def duplicate_error(payload: ClientCreate | ClientUpdate, client: Client) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": "Клиент с таким полным ФИО уже есть",
            "duplicate_keys": build_duplicate_check_keys(payload),
            "client_id": client.id,
            "patient_number": client.patient_number,
            "full_name": client_full_name(client),
        },
    )


def latest_encounter_subquery():
    return (
        select(
            Encounter.id.label("encounter_id"),
            Encounter.client_id.label("client_id"),
            Encounter.encounter_date.label("encounter_date"),
            Encounter.created_at.label("created_at"),
            func.row_number()
            .over(
                partition_by=Encounter.client_id,
                order_by=(Encounter.created_at.desc(), Encounter.id.desc()),
            )
            .label("row_number"),
        )
        .where(Encounter.deleted_at.is_(None))
        .subquery()
    )


CLIENT_SEARCH_FIELDS = (
    Client.last_name,
    Client.first_name,
    Client.middle_name,
    Client.phone,
    Client.snils,
    Client.oms_policy,
    Client.document_type,
    Client.document_series,
    Client.document_number,
    Client.address_text,
    Client.registration_text,
    Client.admission_category,
    Client.reference_number,
    Client.card_number,
    Client.journal_number,
    Client.profession,
    Client.work_place,
    Client.organization,
    Client.mkb10,
)

CLIENT_SEARCH_COLUMNS = (
    Client.id,
    Client.patient_number,
    Client.created_at,
    Client.last_name,
    Client.first_name,
    Client.middle_name,
    Client.birth_date,
    Client.phone,
    Client.document_type,
    Client.document_series,
    Client.document_number,
    Client.snils,
    Client.address_text,
    Client.registration_text,
    Client.admission_category,
    Client.reference_number,
    Client.notes,
    Client.encounter_date_text,
    Client.card_number,
    Client.profession,
    Client.work_place,
    Client.organization,
    Client.real_date_text,
)


def client_full_name_expr():
    return (
        func.coalesce(Client.last_name, "")
        .concat(" ")
        .concat(func.coalesce(Client.first_name, ""))
        .concat(" ")
        .concat(func.coalesce(Client.middle_name, ""))
    )


def client_search_text_expr():
    full_name = client_full_name_expr()
    expression = func.coalesce(cast(Client.patient_number, String), "")
    for field in CLIENT_SEARCH_FIELDS:
        expression = expression.concat(" ").concat(func.coalesce(field, ""))
    return func.lower(expression.concat(" ").concat(func.replace(full_name, " ", "")))


def client_search_conditions(value: str):
    tokens = [token.lower() for token in value.split() if token]
    conditions = []
    if tokens:
        search_text = client_search_text_expr()
        conditions.append(and_(*[search_text.ilike(f"%{token}%") for token in tokens]))

    if value.isdigit() and len(value) <= 9:
        conditions.insert(0, Client.patient_number == int(value))

    date_value = parse_search_date(value)
    if date_value is not None:
        conditions.insert(0, Client.birth_date == date_value)

    return conditions


def apply_client_filters_and_order(
    query,
    value: str,
    encounter_date: date | None,
    encounter_date_from: date | None = None,
    encounter_date_to: date | None = None,
):
    query = query.where(Client.deleted_at.is_(None))
    if value:
        query = query.where(or_(*client_search_conditions(value)))

    range_from = encounter_date_from or encounter_date
    range_to = encounter_date_to or encounter_date

    if range_from is not None or range_to is not None:
        latest_encounter = latest_encounter_subquery()
        query = query.join(latest_encounter, latest_encounter.c.client_id == Client.id).where(
            latest_encounter.c.row_number == 1,
        )
        if range_from is not None:
            query = query.where(latest_encounter.c.encounter_date >= range_from)
        if range_to is not None:
            query = query.where(latest_encounter.c.encounter_date <= range_to)
        return (
            query.order_by(
                latest_encounter.c.encounter_date.desc(),
                latest_encounter.c.created_at.desc(),
                latest_encounter.c.encounter_id.desc(),
                Client.patient_number.desc(),
            )
        )

    if not value:
        return query.order_by(Client.created_at.desc(), Client.id.desc())

    pattern = f"%{value}%"
    full_name = func.lower(client_full_name_expr())
    rank_conditions = []
    if value.isdigit() and len(value) <= 9:
        rank_conditions.append((Client.patient_number == int(value), -2))
    date_value = parse_search_date(value)
    if date_value is not None:
        rank_conditions.append((Client.birth_date == date_value, -1))
    rank_conditions.extend(
        [
            (func.lower(Client.last_name) == value.lower(), 0),
            (Client.last_name.ilike(f"{value}%"), 1),
            (Client.last_name.ilike(pattern), 2),
            (full_name.ilike(f"{value.lower()}%"), 3),
        ]
    )
    surname_rank = case(*rank_conditions, else_=9)
    return query.order_by(
        surname_rank.asc(),
        Client.last_name.asc(),
        Client.first_name.asc(),
        Client.patient_number.asc(),
    )


@router.get("/search", response_model=list[ClientSearchRead])
def search_clients(
    search: str | None = Query(default=None),
    encounter_date: date | None = Query(default=None),
    encounter_date_from: date | None = Query(default=None),
    encounter_date_to: date | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[ClientSearchRead]:
    value = search.strip() if search else ""
    query = apply_client_filters_and_order(
        select(*CLIENT_SEARCH_COLUMNS),
        value,
        encounter_date,
        encounter_date_from,
        encounter_date_to,
    ).offset(offset).limit(limit)
    rows = db.execute(query).mappings().all()
    client_ids = [row["id"] for row in rows]
    services_by_client = latest_services_by_client_ids(db, client_ids)
    latest_encounter_created_at_by_client = latest_encounter_created_at_by_client_ids(db, client_ids)
    result: list[ClientSearchRead] = []
    for row in rows:
        payload = dict(row)
        payload["services"] = services_by_client.get(row["id"], [])
        payload["latest_encounter_created_at"] = latest_encounter_created_at_by_client.get(row["id"])
        result.append(ClientSearchRead.model_validate(payload))
    return result


@router.get("", response_model=list[ClientRead])
def list_clients(
    search: str | None = Query(default=None),
    encounter_date: date | None = Query(default=None),
    encounter_date_from: date | None = Query(default=None),
    encounter_date_to: date | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[ClientRead]:
    value = search.strip() if search else ""
    query = apply_client_filters_and_order(
        select(Client),
        value,
        encounter_date,
        encounter_date_from,
        encounter_date_to,
    ).offset(offset).limit(limit)
    clients = db.execute(query).scalars().all()
    return serialize_clients(db, clients)


@router.get("/deleted", response_model=list[DeletedClientRead])
def list_deleted_clients(
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[DeletedClientRead]:
    query = select(Client).where(Client.deleted_at.is_not(None))
    value = search.strip() if search else ""
    if value:
        pattern = f"%{value}%"
        query = query.where(
            or_(
                Client.last_name.ilike(pattern),
                Client.first_name.ilike(pattern),
                Client.middle_name.ilike(pattern),
                Client.phone.ilike(pattern),
                Client.card_number.ilike(pattern),
                cast(Client.patient_number, String).ilike(pattern),
            )
        )

    query = query.order_by(Client.deleted_at.desc()).limit(limit)
    clients = db.execute(query).scalars().all()
    return [
        DeletedClientRead(
            id=client.id,
            patient_number=client.patient_number,
            full_name=client_full_name(client),
            birth_date=client.birth_date,
            deleted_at=client.deleted_at,
        )
        for client in clients
        if client.deleted_at is not None
    ]


@router.get("/{client_id}", response_model=ClientRead)
def get_client(client_id: int, db: Session = Depends(get_db)) -> ClientRead:
    client = db.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")
    return serialize_client(db, client)


@router.post("", response_model=ClientRead)
def create_client(payload: ClientCreate, db: Session = Depends(get_db)) -> ClientRead:
    normalized_data = normalize_payload(payload)
    normalized_payload = ClientCreate(**normalized_data)
    possible_duplicate = find_duplicate(db, normalized_payload)
    if possible_duplicate is not None:
        raise duplicate_error(normalized_payload, possible_duplicate)

    next_patient_number = get_next_patient_number(db)
    normalized_data["card_number"] = normalized_data.get("card_number") or f"{next_patient_number:07d}"
    created_by_user_id = get_system_user_id(db)
    client = Client(**normalized_data, patient_number=next_patient_number, created_by_user_id=created_by_user_id)
    db.add(client)
    db.flush()
    db.add(
        MedicalRecord(
            client_id=client.id,
            card_number=client.card_number or f"{client.patient_number:07d}",
            opened_at=date.today(),
            oms_policy=client.oms_policy,
            work_place=client.work_place or client.organization,
            position=client.profession,
            diagnosis=client.indications,
            mkb10=client.mkb10,
            notes=client.notes,
        )
    )
    db.commit()
    db.refresh(client)
    write_audit_log(
        db,
        entity_type="client",
        entity_id=client.id,
        action="create",
        user_id=created_by_user_id,
        payload_json={"full_name": f"{client.last_name} {client.first_name}"},
    )
    db.commit()
    return ClientRead.model_validate(client)


@router.put("/{client_id}", response_model=ClientRead)
def update_client(client_id: int, payload: ClientUpdate, db: Session = Depends(get_db)) -> ClientRead:
    client = db.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")

    normalized_data = normalize_payload(payload)
    normalized_payload = ClientUpdate(**normalized_data)
    possible_duplicate = find_duplicate(db, normalized_payload, exclude_client_id=client_id)
    if possible_duplicate is not None:
        raise duplicate_error(normalized_payload, possible_duplicate)

    for key, value in normalized_data.items():
        setattr(client, key, value)

    updated_by_user_id = get_system_user_id(db)
    db.commit()
    db.refresh(client)
    write_audit_log(
        db,
        entity_type="client",
        entity_id=client.id,
        action="update",
        user_id=updated_by_user_id,
        payload_json={"full_name": f"{client.last_name} {client.first_name}"},
    )
    db.commit()
    return ClientRead.model_validate(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> None:
    client = db.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")

    client.deleted_at = datetime.now(timezone.utc)
    full_name = client_full_name(client)
    deleted_at_iso = client.deleted_at.isoformat()
    deleted_by_user_id = actor_user_id(db, current_user)
    write_audit_log(
        db,
        entity_type="client",
        entity_id=client.id,
        action="delete",
        user_id=deleted_by_user_id,
        payload_json={
            "full_name": full_name,
            "patient_number": client.patient_number,
            "deleted_at": deleted_at_iso,
        },
    )
    db.commit()

    try:
        send_deletion_notification(
            subject=f"Удален клиент №{client.patient_number}",
            body=build_deletion_email_body(
                entity_label="клиент",
                entity_id=client.id,
                deleted_by=current_user.full_name if current_user is not None else None,
                deleted_at=deleted_at_iso,
                details={
                    "ФИО": full_name,
                    "Номер пациента": client.patient_number,
                },
            ),
        )
    except Exception:
        # Email must not block the operator workflow; audit log already keeps the deletion.
        pass


@router.post("/{client_id}/restore", response_model=ClientRead)
def restore_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> ClientRead:
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")
    if client.deleted_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Клиент не находится в удаленных")

    client.deleted_at = None
    restored_by_user_id = actor_user_id(db, current_user)
    db.commit()
    db.refresh(client)
    write_audit_log(
        db,
        entity_type="client",
        entity_id=client.id,
        action="restore",
        user_id=restored_by_user_id,
        payload_json={"full_name": client_full_name(client), "patient_number": client.patient_number},
    )
    db.commit()
    return ClientRead.model_validate(client)
