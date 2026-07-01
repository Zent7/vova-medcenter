from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Encounter(TimestampMixin, Base):
    __tablename__ = "encounters"

    id: Mapped[int] = mapped_column(primary_key=True)
    legacy_source_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True, index=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id"), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    visit_type_id: Mapped[int | None] = mapped_column(ForeignKey("visit_types.id"), nullable=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    encounter_date: Mapped[date] = mapped_column(Date, index=True)
    payment_type: Mapped[str] = mapped_column(String(50))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    final_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    suppressed_doctor_role_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
