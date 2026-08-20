from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.xml_export import XmlExportCleanupResponse, XmlExportDayRead, XmlExportDeleteResponse
from app.services.xml_exports import (
    build_xml_export_archive,
    cleanup_old_xml_exports,
    delete_xml_day,
    delete_xml_document_by_id,
    list_xml_export_days,
)

router = APIRouter()


@router.get("/days", response_model=list[XmlExportDayRead])
def list_days(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[XmlExportDayRead]:
    return [XmlExportDayRead(**day.__dict__) for day in list_xml_export_days(db)]


@router.get("/days/{export_date}/archive")
def download_day_archive(
    export_date: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        file_name, content = build_xml_export_archive(db, export_date)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/documents/{generated_document_id}", response_model=XmlExportDeleteResponse)
def delete_document(
    generated_document_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> XmlExportDeleteResponse:
    try:
        result = delete_xml_document_by_id(db, generated_document_id, reason="manual")
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OSError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return XmlExportDeleteResponse(
        deleted_count=result.deleted_count,
        missing_count=result.missing_count,
        message="XML file deleted.",
    )


@router.delete("/days/{export_date}", response_model=XmlExportDeleteResponse)
def delete_day(
    export_date: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> XmlExportDeleteResponse:
    try:
        result = delete_xml_day(db, export_date, reason="manual")
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OSError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return XmlExportDeleteResponse(
        deleted_count=result.deleted_count,
        missing_count=result.missing_count,
        message="XML day files deleted.",
    )


@router.post("/cleanup", response_model=XmlExportCleanupResponse)
def cleanup(
    retention_days: int | None = Query(default=None, ge=1),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> XmlExportCleanupResponse:
    days = retention_days or settings.xml_exports_retention_days
    try:
        result = cleanup_old_xml_exports(db, retention_days=days)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OSError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return XmlExportCleanupResponse(
        deleted_count=result.deleted_count,
        missing_count=result.missing_count,
        retention_days=days,
        message="Old XML export files cleaned up.",
    )
