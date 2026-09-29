from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import require_admin
from app.db.session import get_db
from app.models.center import Center
from app.models.encounter import Encounter
from app.models.encounter_service import EncounterService
from app.models.generated_document import GeneratedDocument
from app.models.payment import Payment
from app.models.user import User
from app.schemas.report import DailySummaryReport, ReportCenterSummary, ReportTotals

router = APIRouter()


def _build_totals(
    centers: Iterable[ReportCenterSummary],
) -> ReportTotals:
    center_rows = list(centers)
    return ReportTotals(
        clients_count=sum(item.clients_count for item in center_rows),
        documents_count=sum(item.documents_count for item in center_rows),
        services_count=sum(item.services_count for item in center_rows),
        revenue=sum((item.revenue for item in center_rows), Decimal("0.00")),
    )


@router.get("/daily-summary", response_model=DailySummaryReport)
def get_daily_summary_report(
    date_from: date = Query(...),
    date_to: date = Query(...),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DailySummaryReport:
    if date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from must be earlier than or equal to date_to",
        )

    centers = db.execute(
        select(Center).where(Center.is_active.is_(True)).order_by(Center.name.asc(), Center.id.asc())
    ).scalars().all()

    clients_by_center = {
        center_id: clients_count
        for center_id, clients_count in db.execute(
            select(Encounter.center_id, func.count(func.distinct(Encounter.client_id)))
            .where(
                Encounter.deleted_at.is_(None),
                Encounter.encounter_date >= date_from,
                Encounter.encounter_date <= date_to,
            )
            .group_by(Encounter.center_id)
        ).all()
    }

    documents_by_center = {
        center_id: documents_count
        for center_id, documents_count in db.execute(
            select(Encounter.center_id, func.count(GeneratedDocument.id))
            .join(Encounter, Encounter.id == GeneratedDocument.encounter_id)
            .where(
                Encounter.deleted_at.is_(None),
                GeneratedDocument.cancelled_at.is_(None),
                func.date(GeneratedDocument.generated_at) >= date_from,
                func.date(GeneratedDocument.generated_at) <= date_to,
            )
            .group_by(Encounter.center_id)
        ).all()
    }

    services_by_center = {
        center_id: services_count
        for center_id, services_count in db.execute(
            select(Encounter.center_id, func.coalesce(func.sum(EncounterService.quantity), 0))
            .join(EncounterService, EncounterService.encounter_id == Encounter.id)
            .where(
                Encounter.deleted_at.is_(None),
                Encounter.encounter_date >= date_from,
                Encounter.encounter_date <= date_to,
            )
            .group_by(Encounter.center_id)
        ).all()
    }

    revenue_by_center = {
        center_id: revenue or Decimal("0.00")
        for center_id, revenue in db.execute(
            select(Encounter.center_id, func.coalesce(func.sum(Payment.amount), 0))
            .join(Encounter, Encounter.id == Payment.encounter_id)
            .where(
                Encounter.deleted_at.is_(None),
                Payment.status == "paid",
                Payment.payment_date >= date_from,
                Payment.payment_date <= date_to,
            )
            .group_by(Encounter.center_id)
        ).all()
    }

    center_rows = [
        ReportCenterSummary(
            center_id=center.id,
            center_code=center.code,
            center_name=center.name,
            clients_count=int(clients_by_center.get(center.id, 0) or 0),
            documents_count=int(documents_by_center.get(center.id, 0) or 0),
            services_count=int(services_by_center.get(center.id, 0) or 0),
            revenue=Decimal(str(revenue_by_center.get(center.id, Decimal("0.00")) or Decimal("0.00"))),
        )
        for center in centers
    ]

    return DailySummaryReport(
        date_from=date_from,
        date_to=date_to,
        totals=_build_totals(center_rows),
        centers=center_rows,
    )
