from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import shutil
from threading import Lock
from urllib.parse import quote, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.document_template import DocumentTemplate
from app.models.generated_document import GeneratedDocument
from app.models.user import User
from app.schemas.document_generation import (
    DocumentGenerateRequest,
    DocumentGenerateResponse,
    DocumentPrintResponse,
    DocumentPrintResultRequest,
    DocumentPrintResultResponse,
    DocumentPrintTicketResponse,
)
from app.schemas.document_template import DocumentTemplateRead
from app.services.blank_forms import BlankServiceError, NoFreeBlankError, spoil_for_generated_document
from app.services.document_generator import generate_document
from app.services.new_xls_templates import NEW_XLS_TEMPLATE_BY_FILE, validate_editable_xls_template
from app.services.template_catalog import (
    SUPPORTED_TEMPLATE_EXTENSIONS,
    get_template_override_path,
    get_templates_root,
    sync_document_template_catalog,
    template_has_override,
    template_supports_layout_editing,
)

router = APIRouter()

_TEMPLATE_FILE_ACCESS_ROLES = {"admin", "chairman"}

_DOCUMENT_MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xml": "application/xml",
}
_PRINT_TICKET_TTL_SECONDS = 120
_print_ticket_lock = Lock()
_print_tickets: dict[str, tuple[Path, datetime]] = {}


def _repair_mojibake(value: str) -> str:
    try:
        return value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return value


def _document_media_type(file_path: Path) -> str:
    return _DOCUMENT_MEDIA_TYPES.get(file_path.suffix.lower(), "application/octet-stream")


def _document_disposition_type(file_path: Path, *, inline_requested: bool) -> str:
    return "inline" if inline_requested else "attachment"


def _public_url_for(request: Request, route_name: str, **path_params: object) -> str:
    route_url = str(request.url_for(route_name, **path_params))
    public_origin = (settings.public_frontend_origin or "").rstrip("/")
    if not public_origin:
        return route_url

    public_parts = urlsplit(public_origin)
    route_parts = urlsplit(route_url)
    encoded_path = quote(route_parts.path, safe="/%")
    request_host = request.headers.get("host", "").split(",", 1)[0].strip()
    if not public_parts.scheme or not public_parts.netloc or request_host != public_parts.netloc:
        return urlunsplit((route_parts.scheme, route_parts.netloc, encoded_path, route_parts.query, route_parts.fragment))

    return urlunsplit(
        (
            public_parts.scheme,
            public_parts.netloc,
            encoded_path,
            route_parts.query,
            route_parts.fragment,
        )
    )


def _resolve_generated_file(file_name: str) -> Path | None:
    generated_dir = Path(settings.generated_documents_dir).resolve()
    file_path = next((path.resolve() for path in generated_dir.rglob(file_name) if path.is_file()), None)
    if file_path is None or (generated_dir not in file_path.parents and file_path != generated_dir):
        return None
    return file_path


def _cleanup_expired_print_tickets(now: datetime) -> None:
    expired = [token for token, (_, expires_at) in _print_tickets.items() if expires_at <= now]
    for token in expired:
        _print_tickets.pop(token, None)


def _role_code(user: User) -> str:
    return user.role.code if user.role is not None else ""


def require_template_file_access(current_user: User = Depends(get_current_user)) -> User:
    if _role_code(current_user) not in _TEMPLATE_FILE_ACCESS_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к файлам шаблонов разрешен только администратору или председателю.",
        )
    return current_user


def _resolve_template_file(template: DocumentTemplate) -> Path | None:
    candidates: list[Path] = []
    try:
        candidates.append(get_template_override_path(template.file_name))
    except ValueError:
        pass
    if template.file_path:
        candidates.append(Path(template.file_path))

    root = get_templates_root()
    names = [template.file_name]
    repaired_name = _repair_mojibake(template.file_name)
    if repaired_name != template.file_name:
        names.append(repaired_name)

    for name in names:
        if name:
            candidates.append(root / name)

    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    return None


def _template_response(template: DocumentTemplate) -> DocumentTemplateRead:
    return DocumentTemplateRead.model_validate(template).model_copy(
        update={
            "supports_layout_editing": template_supports_layout_editing(template.file_name),
            "has_override": template_has_override(template.file_name),
        }
    )


@router.get("/templates", response_model=list[DocumentTemplateRead])
def list_document_templates(db: Session = Depends(get_db)) -> list[DocumentTemplateRead]:
    templates = db.execute(select(DocumentTemplate).where(DocumentTemplate.is_active.is_(True))).scalars().all()
    return [_template_response(item) for item in templates]


@router.post("/templates/refresh", response_model=list[DocumentTemplateRead])
def refresh_document_templates(
    _: User = Depends(require_template_file_access),
    db: Session = Depends(get_db),
) -> list[DocumentTemplateRead]:
    sync_document_template_catalog(db)
    db.commit()
    templates = db.execute(select(DocumentTemplate).where(DocumentTemplate.is_active.is_(True))).scalars().all()
    return [_template_response(item) for item in templates]


@router.get("/templates/{template_id}/file")
def open_document_template(
    template_id: int,
    _: User = Depends(require_template_file_access),
    db: Session = Depends(get_db),
) -> FileResponse:
    template = db.get(DocumentTemplate, template_id)
    if template is None or not template.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")

    file_path = _resolve_template_file(template)
    if file_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл шаблона не найден")

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type=_document_media_type(file_path),
        content_disposition_type=_document_disposition_type(file_path, inline_requested=True),
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


@router.post("/templates/{template_id}/replace", response_model=DocumentTemplateRead)
def replace_document_template(
    template_id: int,
    file: UploadFile = File(...),
    _: User = Depends(require_template_file_access),
    db: Session = Depends(get_db),
) -> DocumentTemplateRead:
    template = db.get(DocumentTemplate, template_id)
    if template is None or not template.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")

    current_path = _resolve_template_file(template) or Path(template.file_path).resolve()
    source_suffix = Path(file.filename or "").suffix.lower()
    target_suffix = current_path.suffix.lower()
    editable_spec = NEW_XLS_TEMPLATE_BY_FILE.get(template.file_name.casefold())
    if source_suffix not in SUPPORTED_TEMPLATE_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Поддерживаются только .docx, .xml, .xls и .xlsx")
    if editable_spec is not None and source_suffix != ".xls":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Свободно редактируемый шаблон должен оставаться в бинарном формате .xls",
        )
    if source_suffix != target_suffix:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Тип файла должен остаться {target_suffix}. Создайте новый шаблон отдельным файлом, если нужен другой тип.",
        )

    target_path = get_template_override_path(template.file_name)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f"{target_path.name}.uploading")
    try:
        with temp_path.open("wb") as target_file:
            shutil.copyfileobj(file.file, target_file)
        if editable_spec is not None:
            try:
                validate_editable_xls_template(temp_path, editable_spec)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        temp_path.replace(target_path)
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Не удалось заменить шаблон: {exc}") from exc
    finally:
        file.file.close()
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    template.file_path = str(target_path)
    template.file_name = target_path.name
    template.template_type = target_suffix.lstrip(".")
    template.output_format = target_suffix.lstrip(".")
    template.is_active = True
    db.commit()
    db.refresh(template)
    return _template_response(template)


@router.post("/templates/{template_id}/reset", response_model=DocumentTemplateRead)
def reset_document_template(
    template_id: int,
    _: User = Depends(require_template_file_access),
    db: Session = Depends(get_db),
) -> DocumentTemplateRead:
    template = db.get(DocumentTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")

    override_path = get_template_override_path(template.file_name)
    bundled_path = (get_templates_root() / template.file_name).resolve()
    if not bundled_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Встроенный шаблон не найден")
    try:
        override_path.unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось удалить клиентскую версию: {exc}",
        ) from exc

    template.file_path = str(bundled_path)
    template.template_type = bundled_path.suffix.lower().lstrip(".")
    template.output_format = template.template_type
    db.commit()
    db.refresh(template)
    return _template_response(template)


@router.post("/generate", response_model=DocumentGenerateResponse)
def generate_document_file(payload: DocumentGenerateRequest, db: Session = Depends(get_db)) -> DocumentGenerateResponse:
    try:
        result = generate_document(
            db,
            template_id=payload.template_id,
            template_code=payload.template_code,
            client_id=payload.client_id,
            encounter_id=payload.encounter_id,
            blank_form_id=payload.blank_form_id,
            print_variant=payload.print_variant,
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except NoFreeBlankError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except BlankServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/print", response_model=DocumentPrintResponse)
def print_document_file(payload: DocumentGenerateRequest, db: Session = Depends(get_db)) -> DocumentPrintResponse:
    try:
        generated = generate_document(
            db,
            template_id=payload.template_id,
            template_code=payload.template_code,
            client_id=payload.client_id,
            encounter_id=payload.encounter_id,
            blank_form_id=payload.blank_form_id,
            print_variant=payload.print_variant,
        )
        db.commit()
        return DocumentPrintResponse(
            **generated.model_dump(),
            printed=False,
            message=f"Документ {generated.output_file_name} сформирован и готов к открытию.",
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except NoFreeBlankError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except BlankServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

@router.post("/print-result", response_model=DocumentPrintResultResponse)
def save_print_result(
    payload: DocumentPrintResultRequest,
    db: Session = Depends(get_db),
) -> DocumentPrintResultResponse:
    document = db.get(GeneratedDocument, payload.generated_document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сформированный документ не найден")

    if payload.success:
        db.commit()
        return DocumentPrintResultResponse(
            generated_document_id=document.id,
            blank_form_id=document.blank_form_id,
            blank_status="issued" if document.blank_form_id else None,
            message="Результат печати подтвержден.",
        )

    try:
        form = spoil_for_generated_document(
            db,
            generated_document_id=document.id,
            reason=payload.reason,
            user_id=1,
        )
        db.commit()
        return DocumentPrintResultResponse(
            generated_document_id=document.id,
            blank_form_id=form.id if form is not None else document.blank_form_id,
            blank_status=form.status if form is not None else None,
            message="Бланк отмечен как испорченный.",
        )
    except BlankServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/generated/{file_name}/print-ticket", response_model=DocumentPrintTicketResponse)
def create_generated_file_print_ticket(
    file_name: str,
    request: Request,
    _: User = Depends(get_current_user),
) -> DocumentPrintTicketResponse:
    file_path = _resolve_generated_file(file_name)
    if file_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Р¤Р°Р№Р» РЅРµ РЅР°Р№РґРµРЅ")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=_PRINT_TICKET_TTL_SECONDS)
    token = secrets.token_urlsafe(32)
    with _print_ticket_lock:
        _cleanup_expired_print_tickets(now)
        _print_tickets[token] = (file_path, expires_at)

    return DocumentPrintTicketResponse(
        file_name=file_path.name,
        file_url=_public_url_for(request, "download_print_ticket_file_named", token=token, file_name=file_path.name),
        expires_in_seconds=_PRINT_TICKET_TTL_SECONDS,
    )


def _download_print_ticket(token: str) -> FileResponse:
    now = datetime.now(timezone.utc)
    with _print_ticket_lock:
        _cleanup_expired_print_tickets(now)
        ticket = _print_tickets.get(token)

    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="РЎСЃС‹Р»РєР° РґР»СЏ РїРµС‡Р°С‚Рё РЅРµ РЅР°Р№РґРµРЅР° РёР»Рё СѓСЃС‚Р°СЂРµР»Р°")

    file_path, expires_at = ticket
    if expires_at <= now or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Р¤Р°Р№Р» РґР»СЏ РїРµС‡Р°С‚Рё РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СЃСЃС‹Р»РєР° СѓСЃС‚Р°СЂРµР»Р°")

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type=_document_media_type(file_path),
        content_disposition_type=_document_disposition_type(file_path, inline_requested=True),
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


@router.get("/print-ticket/{token}/{file_name}", name="download_print_ticket_file_named")
def download_print_ticket_file_named(token: str, file_name: str) -> FileResponse:
    return _download_print_ticket(token)


@router.get("/print-ticket/{token}", name="download_print_ticket_file")
def download_print_ticket_file(token: str) -> FileResponse:
    return _download_print_ticket(token)


@router.get("/generated/{file_name}")
def download_generated_file(
    file_name: str,
    _: User = Depends(get_current_user),
) -> FileResponse:
    file_path = _resolve_generated_file(file_name)
    if file_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type=_document_media_type(file_path),
        content_disposition_type=_document_disposition_type(file_path, inline_requested=True),
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )
