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
from app.models.document_template import DocumentTemplate
from app.models.generated_document import GeneratedDocument


@dataclass(frozen=True)
class XmlExportDay:
    date: str
    total_count: int
    available_count: int
    deleted_count: int


@dataclass(frozen=True)
class XmlDeleteResult:
    deleted_count: int
    missing_count: int


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


def _local_export_date(document: GeneratedDocument) -> date:
    return _as_utc(document.generated_at).astimezone(xml_exports_timezone()).date()


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


def list_xml_export_days(db: Session) -> list[XmlExportDay]:
    totals: dict[str, dict[str, int]] = {}
    for document in db.execute(_xml_documents_query()).scalars().all():
        day = _local_export_date(document).isoformat()
        counts = totals.setdefault(day, {"total": 0, "available": 0, "deleted": 0})
        counts["total"] += 1
        path = _document_path(document)
        if document.file_deleted_at is None and path.is_file() and _is_safe_generated_path(path):
            counts["available"] += 1
        else:
            counts["deleted"] += 1

    return [
        XmlExportDay(
            date=day,
            total_count=counts["total"],
            available_count=counts["available"],
            deleted_count=counts["deleted"],
        )
        for day, counts in sorted(totals.items(), reverse=True)
    ]


def xml_documents_for_day(db: Session, export_date: str) -> list[GeneratedDocument]:
    target_date = _parse_export_date(export_date)
    return [
        document
        for document in db.execute(_xml_documents_query()).scalars().all()
        if _local_export_date(document) == target_date
    ]


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
    for document in db.execute(_xml_documents_query()).scalars().all():
        if _local_export_date(document) >= cutoff_date:
            continue
        result = delete_xml_document_file(db, document, "retention")
        deleted += result.deleted_count
        missing += result.missing_count
    return XmlDeleteResult(deleted_count=deleted, missing_count=missing)
