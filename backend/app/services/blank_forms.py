"""Бизнес-логика учёта номерных бланков.

Сервис отвечает за:
* создание партии бланков (массовое создание blank_forms внутри диапазона);
* выдачу следующего свободного номера в транзакции с блокировкой строки
  (SELECT ... FOR UPDATE SKIP LOCKED);
* пометку бланка как испорченного;
* идемпотентную выдачу номера для одного и того же документа.

Сервис не зависит от FastAPI — его легко вызывать из любого роутера или
другого сервиса (например, из `services/document_generator.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from sqlalchemy import Integer, and_, case, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.blank_form import (
    BLANK_STATUS_CANCELLED,
    BLANK_STATUS_FREE,
    BLANK_STATUS_ISSUED,
    BLANK_STATUS_SPOILED,
    BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
    BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
    BLANK_TYPE_GUARD_MEDICAL_CERTIFICATE,
    BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
    NUMBERED_BLANK_TYPES,
    BlankBatch,
    BlankForm,
    BlankType,
)
from app.models.client import Client
from app.models.client_document import ClientDocument
from app.models.document_journal import DocumentJournalEntry
from app.models.document_template import DocumentTemplate
from app.models.encounter import Encounter
from app.models.generated_document import GeneratedDocument
from app.models.medical_record import MedicalRecordEntry
from app.models.user import User
from app.services.audit import write_audit_log


AUTO_NUMBER_BATCH_COMMENT = "Автонумерация по сокращению услуги"
AUTO_NUMBER_LOCK_NAMESPACE = 1_870_341_624


class BlankServiceError(Exception):
    """Базовая ошибка сервиса бланков."""


class NoFreeBlankError(BlankServiceError):
    """Свободных бланков для выдачи не осталось."""


class BlankRangeOverlapError(BlankServiceError):
    """Диапазон номеров пересекается с уже существующим."""


class BlankRangeInvalidError(BlankServiceError):
    """Невалидный диапазон номеров."""


class BlankIssuanceContextError(BlankServiceError):
    """Недостаточно контекста для выдачи номерного бланка."""


def resolve_blank_type_for_series(blank_type: str, series: str | None) -> str:
    """Correct legacy generic requests for specialized LMK and GIMS series."""

    if str(blank_type or "").strip() != BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE:
        return blank_type

    normalized_series = str(series or "").strip().casefold()
    if normalized_series.startswith(("лмк", "lmk")):
        return BLANK_TYPE_LMK_MEDICAL_CERTIFICATE
    if normalized_series.startswith(("гимс", "gims")):
        return BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE
    return blank_type


@dataclass
class IssueRequest:
    blank_type: str
    client_id: int
    center_id: int | None
    encounter_id: int | None
    generated_document_id: int | None
    client_document_id: int | None
    user_id: int | None


def format_full_number(series: str | None, number_value: int, width: int) -> str:
    """Собирает полный номер бланка с ведущими нулями."""

    width = max(1, int(width or 1))
    body = f"{int(number_value):0{width}d}"
    series_part = (series or "").strip()
    return f"{series_part}{body}" if series_part else body


def detect_number_width(value: str | int | None, fallback: int = 6) -> int:
    """Определяет ширину номера по строке вида "000001"."""

    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    digits = "".join(ch for ch in text if ch.isdigit())
    return max(len(digits), fallback)


def parse_number_input(value: str | int | None) -> int:
    """Преобразует строковое представление номера в целое число.

    Допустимы значения вида ``"000001"`` — ведущие нули отбрасываются для
    хранения в базе, но сохраняются в ширине номера для последующей
    сборки полного номера.
    """

    if value is None:
        raise BlankRangeInvalidError("Не указан номер")
    if isinstance(value, int):
        return int(value)
    text = str(value).strip()
    if not text:
        raise BlankRangeInvalidError("Не указан номер")
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        raise BlankRangeInvalidError(f"Номер должен быть числом: {value!r}")
    return int(digits)


def list_blank_types(db: Session) -> list[BlankType]:
    order_by_code = case(
        {code: index for index, (code, _name) in enumerate(NUMBERED_BLANK_TYPES)},
        value=BlankType.code,
        else_=len(NUMBERED_BLANK_TYPES),
    )
    return list(
        db.execute(
            select(BlankType)
            .where(BlankType.is_active.is_(True))
            .order_by(order_by_code, BlankType.id.asc())
        ).scalars()
    )


def get_blank_type(db: Session, code: str) -> BlankType | None:
    return db.execute(select(BlankType).where(BlankType.code == code)).scalar_one_or_none()


def _aggregate_status_counts(rows: Iterable[tuple[int, str, int]]) -> dict[int, dict[str, int]]:
    result: dict[int, dict[str, int]] = {}
    for batch_id, status, count in rows:
        bucket = result.setdefault(
            batch_id,
            {
                "free": 0,
                "issued": 0,
                "spoiled": 0,
                "cancelled": 0,
            },
        )
        if status in bucket:
            bucket[status] = int(count or 0)
    return result


def list_batches(
    db: Session,
    *,
    blank_type: str | None = None,
    center_id: int | None = None,
) -> list[tuple[BlankBatch, dict[str, int]]]:
    query = (
        select(BlankBatch)
        .where(BlankBatch.deleted_at.is_(None))
        .order_by(BlankBatch.created_at.desc(), BlankBatch.id.desc())
    )
    if blank_type:
        query = query.where(BlankBatch.blank_type == blank_type)
    if center_id is not None:
        query = query.where(BlankBatch.center_id == center_id)
    batches = list(db.execute(query).scalars())

    if not batches:
        return []

    batch_ids = [batch.id for batch in batches]
    rows = db.execute(
        select(BlankForm.batch_id, BlankForm.status, func.count(BlankForm.id))
        .where(BlankForm.batch_id.in_(batch_ids))
        .group_by(BlankForm.batch_id, BlankForm.status)
    ).all()
    counts = _aggregate_status_counts(rows)

    result: list[tuple[BlankBatch, dict[str, int]]] = []
    for batch in batches:
        result.append((batch, counts.get(batch.id, {"free": 0, "issued": 0, "spoiled": 0, "cancelled": 0})))
    return result


def create_batch(
    db: Session,
    *,
    blank_type: str,
    series: str | None,
    number_from_input: str | int,
    number_to_input: str | int,
    received_at: date | None,
    comment: str | None,
    center_id: int | None,
    user_id: int | None,
) -> BlankBatch:
    blank_type_record = get_blank_type(db, blank_type)
    if blank_type_record is None or not blank_type_record.is_active:
        raise BlankServiceError(f"Неизвестный тип бланка: {blank_type}")

    number_from = parse_number_input(number_from_input)
    number_to = parse_number_input(number_to_input)
    if number_to < number_from:
        raise BlankRangeInvalidError("Конечный номер партии меньше начального")
    quantity = number_to - number_from + 1
    if quantity <= 0:
        raise BlankRangeInvalidError("Партия не должна быть пустой")

    width = max(
        detect_number_width(number_from_input, fallback=6),
        detect_number_width(number_to_input, fallback=6),
    )
    series_clean = (series or "").strip() or None

    # Проверка пересечения диапазонов в рамках того же center+series+type.
    overlap = db.execute(
        select(BlankForm.full_number)
        .where(
            and_(
                BlankForm.blank_type == blank_type,
                BlankForm.center_id.is_(center_id) if center_id is None else BlankForm.center_id == center_id,
                BlankForm.series.is_(series_clean) if series_clean is None else BlankForm.series == series_clean,
                BlankForm.number_value >= number_from,
                BlankForm.number_value <= number_to,
            )
        )
        .limit(1)
    ).scalar_one_or_none()
    if overlap is not None:
        raise BlankRangeOverlapError(
            f"Диапазон пересекается с уже существующим номером {overlap}"
        )

    batch = BlankBatch(
        center_id=center_id,
        blank_type=blank_type,
        series=series_clean,
        number_from=number_from,
        number_to=number_to,
        number_width=width,
        quantity=quantity,
        received_at=received_at,
        comment=comment,
        created_by_user_id=user_id,
    )
    db.add(batch)
    db.flush()

    forms = [
        BlankForm(
            batch_id=batch.id,
            center_id=center_id,
            blank_type=blank_type,
            series=series_clean,
            number_value=value,
            full_number=format_full_number(series_clean, value, width),
            status=BLANK_STATUS_FREE,
        )
        for value in range(number_from, number_to + 1)
    ]
    db.bulk_save_objects(forms)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise BlankRangeOverlapError(
            "Один из номеров уже существует в базе. Партия не создана."
        ) from exc

    write_audit_log(
        db,
        entity_type="blank_batch",
        entity_id=batch.id,
        action="create",
        user_id=user_id or 1,
        center_id=center_id,
        payload_json={
            "blank_type": blank_type,
            "series": series_clean,
            "number_from": number_from,
            "number_to": number_to,
            "quantity": quantity,
        },
    )
    return batch


def list_forms(
    db: Session,
    *,
    blank_type: str | None = None,
    batch_id: int | None = None,
    status: str | None = None,
    center_id: int | None = None,
    search: str | None = None,
    limit: int = 200,
) -> list[BlankForm]:
    query = select(BlankForm)
    if blank_type:
        query = query.where(BlankForm.blank_type == blank_type)
    if batch_id is not None:
        query = query.where(BlankForm.batch_id == batch_id)
    if status:
        query = query.where(BlankForm.status == status)
    if center_id is not None:
        query = query.where(BlankForm.center_id == center_id)
    if search:
        like = f"%{search.strip()}%"
        query = query.where(BlankForm.full_number.ilike(like))
    query = query.order_by(BlankForm.number_value.asc(), BlankForm.id.asc()).limit(limit)
    return list(db.execute(query).scalars())


def stats(db: Session, *, center_id: int | None = None) -> list[dict[str, object]]:
    types = list_blank_types(db)
    if not types:
        return []
    type_codes = [bt.code for bt in types]

    query = select(BlankForm.blank_type, BlankForm.status, func.count(BlankForm.id)).where(
        BlankForm.blank_type.in_(type_codes)
    )
    if center_id is not None:
        query = query.where(BlankForm.center_id == center_id)
    rows = db.execute(query.group_by(BlankForm.blank_type, BlankForm.status)).all()

    by_type: dict[str, dict[str, int]] = {
        bt.code: {"free": 0, "issued": 0, "spoiled": 0, "cancelled": 0} for bt in types
    }
    for blank_type, status, count in rows:
        if blank_type in by_type and status in by_type[blank_type]:
            by_type[blank_type][status] = int(count or 0)

    result = []
    for bt in types:
        bucket = by_type.get(bt.code, {"free": 0, "issued": 0, "spoiled": 0, "cancelled": 0})
        total = sum(bucket.values())
        result.append(
            {
                "blank_type": bt.code,
                "blank_type_name": bt.name,
                "total": total,
                **bucket,
            }
        )
    return result


def list_free_series(
    db: Session,
    *,
    blank_type: str,
    center_id: int | None = None,
) -> list[dict[str, object]]:
    forms = list_forms(
        db,
        blank_type=blank_type,
        status=BLANK_STATUS_FREE,
        center_id=center_id,
        limit=1000,
    )
    grouped: dict[str | None, dict[str, object]] = {}
    for form in forms:
        bucket = grouped.setdefault(
            form.series,
            {
                "series": form.series,
                "free_count": 0,
                "next_form_id": form.id,
                "next_full_number": form.full_number,
            },
        )
        bucket["free_count"] = int(bucket["free_count"]) + 1
    return sorted(
        grouped.values(),
        key=lambda item: ((item["series"] or "") == "", item["series"] or ""),
    )


def get_next_free_form(
    db: Session,
    *,
    blank_type: str,
    center_id: int | None = None,
    series: str | None = None,
) -> BlankForm | None:
    query = (
        select(BlankForm)
        .where(
            BlankForm.blank_type == blank_type,
            BlankForm.status == BLANK_STATUS_FREE,
        )
        .order_by(BlankForm.number_value.asc(), BlankForm.id.asc())
        .limit(1)
    )
    if center_id is not None:
        query = query.where(BlankForm.center_id == center_id)
    series_clean = (series or "").strip()
    if series is not None:
        query = query.where(BlankForm.series == (series_clean or None))
    return db.execute(query).scalar_one_or_none()


def get_form_by_printed_number(
    db: Session,
    *,
    blank_type: str,
    center_id: int | None,
    series: str,
    number_input: str | int,
) -> BlankForm | None:
    """Находит конкретный типографский бланк без выбора следующего номера."""

    series_clean = (series or "").strip()
    if not series_clean:
        raise BlankRangeInvalidError("Укажите серию бланка")

    number_value = parse_number_input(number_input)
    query = select(BlankForm).where(
        BlankForm.blank_type == blank_type,
        BlankForm.series == series_clean,
        BlankForm.number_value == number_value,
    )
    if center_id is not None:
        query = query.where(BlankForm.center_id == center_id)
    return db.execute(query.order_by(BlankForm.id.asc()).limit(1)).scalar_one_or_none()


def create_auto_number_form(
    db: Session,
    *,
    blank_type: str,
    center_id: int | None,
    series: str,
    user_id: int | None = None,
) -> BlankForm:
    """Создаёт следующий свободный номер для серий без заранее заведённых бланков."""

    series_clean = (series or "").strip()
    if not series_clean:
        raise BlankRangeInvalidError("Для автонумерации укажите серию или сокращение услуги")

    blank_type_record = get_blank_type(db, blank_type)
    if blank_type_record is None or not blank_type_record.is_active:
        raise BlankServiceError(f"Неизвестный тип бланка: {blank_type}")

    # Автоматические номера образуют одну последовательность внутри медцентра,
    # независимо от типа справки и её серии. Строгие бланки из вручную
    # заведённых партий в этот счётчик не входят.
    #
    # PostgreSQL advisory lock не позволяет двум параллельным запросам получить
    # один и тот же следующий номер, даже если они создают разные серии.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            select(
                func.pg_advisory_xact_lock(
                    cast(AUTO_NUMBER_LOCK_NAMESPACE, Integer),
                    cast(int(center_id or 0), Integer),
                )
            )
        )

    batch = db.execute(
        select(BlankBatch)
        .where(
            BlankBatch.deleted_at.is_(None),
            BlankBatch.blank_type == blank_type,
            BlankBatch.center_id.is_(center_id) if center_id is None else BlankBatch.center_id == center_id,
            BlankBatch.series == series_clean,
            BlankBatch.comment == AUTO_NUMBER_BATCH_COMMENT,
        )
        .order_by(BlankBatch.id.asc())
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()
    if batch is None:
        batch = BlankBatch(
            center_id=center_id,
            blank_type=blank_type,
            series=series_clean,
            number_from=1,
            number_to=0,
            number_width=7,
            quantity=0,
            received_at=date.today(),
            comment=AUTO_NUMBER_BATCH_COMMENT,
            created_by_user_id=user_id,
        )
        db.add(batch)
        db.flush()

    max_number = db.execute(
        select(func.max(BlankForm.number_value))
        .join(BlankBatch, BlankBatch.id == BlankForm.batch_id)
        .where(
            BlankBatch.comment == AUTO_NUMBER_BATCH_COMMENT,
            BlankForm.center_id.is_(center_id) if center_id is None else BlankForm.center_id == center_id,
        )
    ).scalar_one_or_none()
    next_number = int(max_number or 0) + 1

    form = BlankForm(
        batch_id=batch.id,
        center_id=center_id,
        blank_type=blank_type,
        series=series_clean,
        number_value=next_number,
        full_number=format_full_number(series_clean, next_number, 7),
        status=BLANK_STATUS_FREE,
    )
    db.add(form)
    try:
        batch.number_to = max(batch.number_to or 0, next_number)
        batch.quantity = int(batch.quantity or 0) + 1
        db.flush()
    except IntegrityError as exc:
        raise BlankRangeOverlapError("Не удалось присвоить уникальный номер. Повторите попытку.") from exc

    write_audit_log(
        db,
        entity_type="blank_form",
        entity_id=form.id,
        action="auto_create",
        user_id=user_id or 1,
        center_id=center_id,
        payload_json={
            "blank_type": blank_type,
            "series": series_clean,
            "full_number": form.full_number,
        },
    )
    return form


def spoil_form(
    db: Session,
    *,
    form_id: int,
    reason: str | None,
    user_id: int | None,
) -> BlankForm:
    form = db.get(BlankForm, form_id)
    if form is None:
        raise BlankServiceError("Бланк не найден")
    if form.status != BLANK_STATUS_FREE:
        raise BlankServiceError(
            "Помечать как испорченный можно только свободный бланк. "
            "Для выданных используйте аннулирование документа."
        )

    form.status = BLANK_STATUS_SPOILED
    form.spoiled_at = datetime.utcnow()
    form.spoiled_by_user_id = user_id
    form.spoiled_reason = (reason or "").strip() or None
    db.flush()

    write_audit_log(
        db,
        entity_type="blank_form",
        entity_id=form.id,
        action="spoil",
        user_id=user_id or 1,
        center_id=form.center_id,
        payload_json={
            "blank_type": form.blank_type,
            "full_number": form.full_number,
            "reason": form.spoiled_reason,
        },
    )
    return form


def release_form(
    db: Session,
    *,
    form_id: int,
    user_id: int | None,
) -> BlankForm:
    """Возвращает ошибочно выданный, но не использованный номер в свободные."""

    form = db.execute(
        select(BlankForm).where(BlankForm.id == form_id).with_for_update()
    ).scalar_one_or_none()
    if form is None:
        raise BlankServiceError("Бланк не найден")
    if form.status != BLANK_STATUS_ISSUED:
        raise BlankServiceError("Освободить можно только выданный бланк")

    released_at = datetime.utcnow()
    release_reason = "Номер освобождён: печать была запущена по ошибке"
    previous_links = {
        "client_id": form.client_id,
        "encounter_id": form.encounter_id,
        "generated_document_id": form.generated_document_id,
        "client_document_id": form.client_document_id,
    }

    generated_query = select(GeneratedDocument).where(GeneratedDocument.blank_form_id == form.id)
    if form.generated_document_id is not None:
        generated_query = select(GeneratedDocument).where(
            or_(
                GeneratedDocument.blank_form_id == form.id,
                GeneratedDocument.id == form.generated_document_id,
            )
        )
    generated_documents = list(db.execute(generated_query).scalars())
    generated_document_ids: list[int] = []
    for document in generated_documents:
        generated_document_ids.append(document.id)
        document.blank_form_id = None
        document.blank_number_snapshot = None
        if document.document_number == form.full_number:
            document.document_number = None
        if document.cancelled_at is None:
            document.cancelled_at = released_at
            document.cancelled_by_user_id = user_id
            document.cancelled_reason = release_reason

    if generated_document_ids:
        journal_entries = db.execute(
            select(DocumentJournalEntry).where(
                DocumentJournalEntry.generated_document_id.in_(generated_document_ids),
                DocumentJournalEntry.deleted_at.is_(None),
            )
        ).scalars()
        for entry in journal_entries:
            entry.deleted_at = released_at

    client_document_query = select(ClientDocument).where(ClientDocument.blank_form_id == form.id)
    if form.client_document_id is not None:
        client_document_query = select(ClientDocument).where(
            or_(
                ClientDocument.blank_form_id == form.id,
                ClientDocument.id == form.client_document_id,
            )
        )
    for document in db.execute(client_document_query).scalars():
        document.blank_form_id = None
        document.blank_number_snapshot = None

    if form.encounter_id is not None:
        conclusion = f"Выдан номерной бланк медицинского заключения №{form.full_number}"
        entries = db.execute(
            select(MedicalRecordEntry).where(
                MedicalRecordEntry.encounter_id == form.encounter_id,
                MedicalRecordEntry.doctor_role_id == "document",
                MedicalRecordEntry.conclusion == conclusion,
            )
        ).scalars()
        for entry in entries:
            db.delete(entry)

    form.status = BLANK_STATUS_FREE
    form.client_id = None
    form.encounter_id = None
    form.generated_document_id = None
    form.client_document_id = None
    form.issued_at = None
    form.issued_by_user_id = None
    form.cancelled_at = None
    form.cancelled_by_user_id = None
    form.cancelled_reason = None
    db.flush()

    write_audit_log(
        db,
        entity_type="blank_form",
        entity_id=form.id,
        action="release",
        user_id=user_id or 1,
        center_id=form.center_id,
        payload_json={
            "blank_type": form.blank_type,
            "full_number": form.full_number,
            **previous_links,
        },
    )
    return form


def issue_next_blank(
    db: Session,
    *,
    blank_type: str,
    client_id: int,
    center_id: int | None,
    encounter_id: int | None = None,
    generated_document_id: int | None = None,
    client_document_id: int | None = None,
    user_id: int | None = None,
) -> BlankForm:
    """Выдаёт следующий свободный номер бланка.

    Идемпотентность:
    * если ``generated_document_id`` уже привязан к бланку — возвращаем его
      без новой выдачи;
    * аналогично для ``client_document_id``.
    """

    if center_id is None:
        raise BlankIssuanceContextError(
            "Нельзя выдать номерной бланк без center_id. Сформируйте документ в контексте обращения."
        )
    if encounter_id is None:
        raise BlankIssuanceContextError(
            "Нельзя выдать номерной бланк без encounter_id. Сформируйте документ по уже оформленному обращению."
        )

    if generated_document_id is not None:
        existing = db.execute(
            select(BlankForm).where(BlankForm.generated_document_id == generated_document_id)
        ).scalar_one_or_none()
        if existing is not None:
            return existing
    if client_document_id is not None:
        existing = db.execute(
            select(BlankForm).where(BlankForm.client_document_id == client_document_id)
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    blank_type_record = get_blank_type(db, blank_type)
    if blank_type_record is None or not blank_type_record.is_active:
        raise BlankServiceError(f"Неизвестный тип бланка: {blank_type}")

    # PostgreSQL: SELECT ... FOR UPDATE SKIP LOCKED — конкурентные транзакции
    # пропускают заблокированные строки и выдают разные номера.
    query = (
        select(BlankForm)
        .where(
            BlankForm.blank_type == blank_type,
            BlankForm.status == BLANK_STATUS_FREE,
        )
        .order_by(BlankForm.number_value.asc(), BlankForm.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if center_id is not None:
        query = query.where(BlankForm.center_id == center_id)

    form: BlankForm | None = db.execute(query).scalar_one_or_none()
    if form is None:
        raise NoFreeBlankError(
            f"Нет свободных бланков для типа «{blank_type_record.name}». "
            "Добавьте новую партию в разделе «Бланки»."
        )

    form.status = BLANK_STATUS_ISSUED
    form.client_id = client_id
    form.encounter_id = encounter_id
    form.generated_document_id = generated_document_id
    form.client_document_id = client_document_id
    form.issued_at = datetime.utcnow()
    form.issued_by_user_id = user_id
    db.flush()

    write_audit_log(
        db,
        entity_type="blank_form",
        entity_id=form.id,
        action="issue",
        user_id=user_id or 1,
        center_id=form.center_id,
        payload_json={
            "blank_type": form.blank_type,
            "full_number": form.full_number,
            "client_id": client_id,
            "encounter_id": encounter_id,
            "generated_document_id": generated_document_id,
            "client_document_id": client_document_id,
        },
    )
    return form


def issue_specific_blank(
    db: Session,
    *,
    form_id: int,
    blank_type: str,
    client_id: int,
    center_id: int | None,
    encounter_id: int | None = None,
    generated_document_id: int | None = None,
    client_document_id: int | None = None,
    user_id: int | None = None,
) -> BlankForm:
    if center_id is None:
        raise BlankIssuanceContextError(
            "Нельзя выдать номерной бланк без center_id. Сформируйте документ в контексте обращения."
        )
    if encounter_id is None:
        raise BlankIssuanceContextError(
            "Нельзя выдать номерной бланк без encounter_id. Сформируйте документ по уже оформленному обращению."
        )

    form = db.get(BlankForm, form_id)
    if form is None:
        raise BlankServiceError("Бланк не найден")
    if form.blank_type != blank_type:
        raise BlankServiceError("Выбранный бланк не соответствует типу документа")
    if form.center_id != center_id:
        raise BlankServiceError("Выбранный бланк относится к другому медцентру")
    if form.status != BLANK_STATUS_FREE:
        raise BlankServiceError("Выбранный бланк уже занят. Найдите следующий свободный номер.")

    form.status = BLANK_STATUS_ISSUED
    form.client_id = client_id
    form.encounter_id = encounter_id
    form.generated_document_id = generated_document_id
    form.client_document_id = client_document_id
    form.issued_at = datetime.utcnow()
    form.issued_by_user_id = user_id
    db.flush()

    write_audit_log(
        db,
        entity_type="blank_form",
        entity_id=form.id,
        action="issue",
        user_id=user_id or 1,
        center_id=form.center_id,
        payload_json={
            "blank_type": form.blank_type,
            "full_number": form.full_number,
            "client_id": client_id,
            "encounter_id": encounter_id,
            "generated_document_id": generated_document_id,
            "client_document_id": client_document_id,
            "mode": "specific",
        },
    )
    return form


def cancel_for_generated_document(
    db: Session,
    *,
    generated_document_id: int,
    reason: str | None,
    user_id: int | None,
) -> BlankForm | None:
    form = db.execute(
        select(BlankForm).where(BlankForm.generated_document_id == generated_document_id)
    ).scalar_one_or_none()
    if form is None or form.status != BLANK_STATUS_ISSUED:
        return form

    form.status = BLANK_STATUS_CANCELLED
    form.cancelled_at = datetime.utcnow()
    form.cancelled_by_user_id = user_id
    form.cancelled_reason = (reason or "").strip() or None
    db.flush()

    write_audit_log(
        db,
        entity_type="blank_form",
        entity_id=form.id,
        action="cancel",
        user_id=user_id or 1,
        center_id=form.center_id,
        payload_json={
            "blank_type": form.blank_type,
            "full_number": form.full_number,
            "generated_document_id": generated_document_id,
            "reason": form.cancelled_reason,
        },
    )
    return form


def spoil_for_generated_document(
    db: Session,
    *,
    generated_document_id: int,
    reason: str | None,
    user_id: int | None,
) -> BlankForm | None:
    document = db.get(GeneratedDocument, generated_document_id)
    form = db.get(BlankForm, document.blank_form_id) if document is not None and document.blank_form_id else None
    if form is None:
        form = db.execute(
            select(BlankForm).where(BlankForm.generated_document_id == generated_document_id)
        ).scalar_one_or_none()
    if form is None:
        return None
    if form.status != BLANK_STATUS_ISSUED:
        return form

    form.status = BLANK_STATUS_SPOILED
    form.spoiled_at = datetime.utcnow()
    form.spoiled_by_user_id = user_id
    form.spoiled_reason = (reason or "").strip() or "Испорчен при печати"
    db.flush()

    if document is not None and document.cancelled_at is None:
        document.cancelled_at = datetime.utcnow()
        document.cancelled_by_user_id = user_id
        document.cancelled_reason = form.spoiled_reason
        db.flush()

    write_audit_log(
        db,
        entity_type="blank_form",
        entity_id=form.id,
        action="spoil_after_print",
        user_id=user_id or 1,
        center_id=form.center_id,
        payload_json={
            "blank_type": form.blank_type,
            "full_number": form.full_number,
            "generated_document_id": generated_document_id,
            "reason": form.spoiled_reason,
        },
    )
    return form



def resolve_required_blank_type(
    template: DocumentTemplate,
    *,
    print_variant: str | None = None,
) -> str | None:
    if str(print_variant or "").strip().casefold() in {"guard", "chod"}:
        return BLANK_TYPE_GUARD_MEDICAL_CERTIFICATE
    if str(print_variant or "").strip().casefold() == "gims":
        return BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE
    if str(print_variant or "").strip().casefold() in {"lmk", "lmk_title", "lmk_certificate"}:
        return BLANK_TYPE_LMK_MEDICAL_CERTIFICATE

    if not template.requires_numbered_blank:
        return None

    blank_type = (template.blank_type or "").strip()
    if not blank_type:
        raise BlankServiceError(
            f"Для шаблона {template.name!r} включен номерной бланк, но не задан blank_type."
        )
    return blank_type


def reuse_blank_for_existing_document(
    db: Session,
    *,
    blank_type: str,
    client_id: int,
    encounter_id: int | None,
    template_id: int,
) -> BlankForm | None:
    """Если для этого клиента/encounter/template уже выдавался номер — возвращаем его."""

    query = (
        select(BlankForm)
        .join(GeneratedDocument, GeneratedDocument.id == BlankForm.generated_document_id)
        .where(
            BlankForm.blank_type == blank_type,
            BlankForm.status.in_([BLANK_STATUS_ISSUED, BLANK_STATUS_CANCELLED]),
            GeneratedDocument.client_id == client_id,
            GeneratedDocument.template_id == template_id,
        )
        .order_by(GeneratedDocument.id.desc())
        .limit(1)
    )
    if encounter_id is not None:
        query = query.where(GeneratedDocument.encounter_id == encounter_id)
    else:
        query = query.where(GeneratedDocument.encounter_id.is_(None))
    return db.execute(query).scalar_one_or_none()


def enrich_form_for_read(
    db: Session, form: BlankForm
) -> dict[str, object]:
    """Готовит словарь под BlankFormRead с подтянутыми полями для UI."""

    payload = {
        "id": form.id,
        "batch_id": form.batch_id,
        "center_id": form.center_id,
        "blank_type": form.blank_type,
        "series": form.series,
        "number_value": form.number_value,
        "full_number": form.full_number,
        "status": form.status,
        "client_id": form.client_id,
        "encounter_id": form.encounter_id,
        "client_document_id": form.client_document_id,
        "generated_document_id": form.generated_document_id,
        "issued_at": form.issued_at,
        "issued_by_user_id": form.issued_by_user_id,
        "spoiled_at": form.spoiled_at,
        "spoiled_by_user_id": form.spoiled_by_user_id,
        "spoiled_reason": form.spoiled_reason,
        "cancelled_at": form.cancelled_at,
        "cancelled_by_user_id": form.cancelled_by_user_id,
        "cancelled_reason": form.cancelled_reason,
        "client_full_name": None,
        "document_label": None,
        "issued_by_name": None,
    }
    if form.client_id:
        client = db.get(Client, form.client_id)
        if client is not None:
            payload["client_full_name"] = " ".join(
                part for part in [client.last_name, client.first_name, client.middle_name] if part
            ).strip()
    if form.generated_document_id:
        document = db.get(GeneratedDocument, form.generated_document_id)
        if document is not None:
            payload["document_label"] = document.file_name
    if form.issued_by_user_id:
        user = db.get(User, form.issued_by_user_id)
        if user is not None:
            payload["issued_by_name"] = user.full_name
    return payload


