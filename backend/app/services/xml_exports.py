from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import zipfile

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.blank_form import BLANK_STATUS_ISSUED, BlankForm
from app.models.client import Client
from app.models.document_template import DocumentTemplate
from app.models.encounter import Encounter
from app.models.generated_document import GeneratedDocument
from app.services.document_generator import (
    generate_miac_xml_for_blank,
    miac_xml_blank_type,
    miac_xml_templates_by_blank_type,
)


# Файлы, которые заменила повторная сборка дня: в выгрузке их больше нет.
XML_REBUILT_REASON = "rebuilt"

MIAC_BLANK_TYPES = tuple(
    blank_type
    for blank_type in (
        miac_xml_blank_type("driver"),
        miac_xml_blank_type("guard"),
        miac_xml_blank_type("gims"),
    )
    if blank_type is not None
)


@dataclass(frozen=True)
class XmlExportDay:
    date: str
    total_count: int
    available_count: int
    deleted_count: int
    blank_count: int = 0


@dataclass(frozen=True)
class XmlDeleteResult:
    deleted_count: int
    missing_count: int


@dataclass(frozen=True)
class XmlBuildSkip:
    client_name: str
    blank_number: str
    reason: str


@dataclass(frozen=True)
class XmlBuildResult:
    date: str
    generated_count: int
    replaced_count: int
    skipped: list[XmlBuildSkip]


def xml_exports_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.xml_exports_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Moscow")


def _generated_root() -> Path:
    return Path(settings.generated_documents_dir).resolve()


def _xml_root() -> Path:
    return (_generated_root() / "xml").resolve()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _local_date(value: datetime) -> date:
    return _as_utc(value).astimezone(xml_exports_timezone()).date()


def _parse_export_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid XML export date. Use YYYY-MM-DD.") from exc


def _document_path(document: GeneratedDocument) -> Path:
    return Path(document.file_path).resolve(strict=False)


def _is_safe_generated_path(path: Path) -> bool:
    root = _generated_root()
    return path == root or root in path.parents


def _xml_documents_query():
    return (
        select(GeneratedDocument)
        .join(DocumentTemplate, GeneratedDocument.template_id == DocumentTemplate.id)
        .where(func.lower(DocumentTemplate.template_type) == "xml")
        .order_by(GeneratedDocument.generated_at.desc(), GeneratedDocument.id.desc())
    )


def _xml_document_days(db: Session) -> list[tuple[GeneratedDocument, date]]:
    """XML лежит в дне выдачи бланка, а не в дне генерации.

    Иначе пересборка дня на следующее утро переносила бы файлы в новый день, и
    за вчера выгрузка осталась бы пустой.
    """

    rows = db.execute(
        _xml_documents_query()
        .outerjoin(BlankForm, GeneratedDocument.blank_form_id == BlankForm.id)
        .add_columns(BlankForm.issued_at)
    ).all()
    return [
        (
            document,
            _local_date(issued_at) if issued_at is not None else _local_date(document.generated_at),
        )
        for document, issued_at in rows
    ]


def _issued_miac_blanks(db: Session) -> list[BlankForm]:
    """Выданные бланки ВУ, ЧОД и ГИМС живых клиентов — основа дневной выгрузки."""

    return list(
        db.execute(
            select(BlankForm)
            .join(Client, BlankForm.client_id == Client.id)
            .join(Encounter, BlankForm.encounter_id == Encounter.id)
            .where(
                BlankForm.status == BLANK_STATUS_ISSUED,
                BlankForm.blank_type.in_(MIAC_BLANK_TYPES),
                BlankForm.issued_at.is_not(None),
                Client.deleted_at.is_(None),
                Encounter.deleted_at.is_(None),
            )
            .order_by(BlankForm.issued_at, BlankForm.id)
        )
        .scalars()
        .all()
    )


def list_xml_export_days(db: Session) -> list[XmlExportDay]:
    totals: dict[str, dict[str, int]] = {}

    def day_counts(day: str) -> dict[str, int]:
        return totals.setdefault(day, {"total": 0, "available": 0, "deleted": 0, "blanks": 0})

    for document, export_date in _xml_document_days(db):
        if document.file_delete_reason == XML_REBUILT_REASON:
            # Файл заменила пересборка дня, показывать его как удалённый незачем.
            continue
        counts = day_counts(export_date.isoformat())
        counts["total"] += 1
        path = _document_path(document)
        if document.file_deleted_at is None and path.is_file() and _is_safe_generated_path(path):
            counts["available"] += 1
        else:
            counts["deleted"] += 1

    for blank in _issued_miac_blanks(db):
        day_counts(_local_date(blank.issued_at).isoformat())["blanks"] += 1

    return [
        XmlExportDay(
            date=day,
            total_count=counts["total"],
            available_count=counts["available"],
            deleted_count=counts["deleted"],
            blank_count=counts["blanks"],
        )
        for day, counts in sorted(totals.items(), reverse=True)
    ]


def xml_documents_for_day(db: Session, export_date: str) -> list[GeneratedDocument]:
    target_date = _parse_export_date(export_date)
    return [document for document, day in _xml_document_days(db) if day == target_date]


def build_xml_export_archive(db: Session, export_date: str) -> tuple[str, bytes]:
    documents = xml_documents_for_day(db, export_date)
    files: list[tuple[GeneratedDocument, Path]] = []
    for document in documents:
        path = _document_path(document)
        if document.file_deleted_at is None and path.is_file() and _is_safe_generated_path(path):
            files.append((document, path))

    if not files:
        raise ValueError("No XML files available for this date.")

    archive = BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for document, path in files:
            archive_name = path.name
            if archive_name in used_names:
                archive_name = f"{document.id}_{archive_name}"
            used_names.add(archive_name)
            zip_file.write(path, archive_name)

    return f"xml-export-{export_date}.zip", archive.getvalue()


def _remove_empty_xml_dirs(path: Path) -> None:
    xml_root = _xml_root()
    current = path.parent
    while current != xml_root and xml_root in current.parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def delete_xml_document_file(db: Session, document: GeneratedDocument, reason: str) -> XmlDeleteResult:
    path = _document_path(document)
    missing = 0
    deleted = 0
    if document.file_deleted_at is None:
        if path.is_file() and _is_safe_generated_path(path):
            path.unlink(missing_ok=True)
            _remove_empty_xml_dirs(path)
            deleted = 1
        else:
            missing = 1
        document.file_deleted_at = datetime.now(timezone.utc)
        document.file_delete_reason = reason
        db.add(document)
    return XmlDeleteResult(deleted_count=deleted, missing_count=missing)


def delete_xml_document_by_id(db: Session, generated_document_id: int, reason: str = "manual") -> XmlDeleteResult:
    document = (
        db.execute(
            _xml_documents_query().where(GeneratedDocument.id == generated_document_id)
        )
        .scalars()
        .first()
    )
    if document is None:
        raise ValueError("XML document not found.")
    return delete_xml_document_file(db, document, reason)


def delete_xml_day(db: Session, export_date: str, reason: str = "manual") -> XmlDeleteResult:
    deleted = 0
    missing = 0
    for document in xml_documents_for_day(db, export_date):
        result = delete_xml_document_file(db, document, reason)
        deleted += result.deleted_count
        missing += result.missing_count
    return XmlDeleteResult(deleted_count=deleted, missing_count=missing)


def cleanup_old_xml_exports(db: Session, retention_days: int | None = None) -> XmlDeleteResult:
    days = settings.xml_exports_retention_days if retention_days is None else retention_days
    if days < 1:
        raise ValueError("XML export retention must be at least 1 day.")

    tzinfo = xml_exports_timezone()
    cutoff_date = (datetime.combine(datetime.now(tzinfo).date(), time.min, tzinfo=tzinfo) - timedelta(days=days)).date()
    deleted = 0
    missing = 0
    for document, export_date in _xml_document_days(db):
        if export_date >= cutoff_date:
            continue
        result = delete_xml_document_file(db, document, "retention")
        deleted += result.deleted_count
        missing += result.missing_count
    return XmlDeleteResult(deleted_count=deleted, missing_count=missing)


def _blank_client_name(db: Session, blank: BlankForm) -> str:
    client = db.get(Client, blank.client_id) if blank.client_id else None
    if client is None:
        return ""
    parts = [client.last_name, client.first_name, client.middle_name]
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def build_xml_day(db: Session, export_date: str) -> XmlBuildResult:
    """Собирает XML за день заново по текущим данным готовых клиентов.

    Старые файлы дня заменяются: справку могли перепечатать после правки данных,
    и в выгрузку должен попасть только последний вариант каждого выданного бланка.
    """

    target_date = _parse_export_date(export_date)
    blanks = [blank for blank in _issued_miac_blanks(db) if _local_date(blank.issued_at) == target_date]
    templates = miac_xml_templates_by_blank_type(db)

    replaced = 0
    for document, day in _xml_document_days(db):
        if day != target_date:
            continue
        replaced += delete_xml_document_file(db, document, XML_REBUILT_REASON).deleted_count

    output_dir = _xml_root() / target_date.isoformat()
    generated = 0
    skipped: list[XmlBuildSkip] = []
    for blank in blanks:
        template = templates.get(blank.blank_type)
        if template is None:
            skipped.append(
                XmlBuildSkip(
                    client_name=_blank_client_name(db, blank),
                    blank_number=blank.full_number,
                    reason="Не найден XML-шаблон МИАЦ для этого типа бланка",
                )
            )
            continue
        try:
            generate_miac_xml_for_blank(db, template=template, blank_form=blank, output_dir=output_dir)
        except ValueError as exc:
            skipped.append(
                XmlBuildSkip(
                    client_name=_blank_client_name(db, blank),
                    blank_number=blank.full_number,
                    reason=str(exc),
                )
            )
            continue
        generated += 1

    return XmlBuildResult(
        date=target_date.isoformat(),
        generated_count=generated,
        replaced_count=replaced,
        skipped=skipped,
    )
