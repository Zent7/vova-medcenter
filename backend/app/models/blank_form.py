from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


# Допустимые статусы конкретного бланка.
BLANK_STATUS_FREE = "free"
BLANK_STATUS_ISSUED = "issued"
BLANK_STATUS_SPOILED = "spoiled"
BLANK_STATUS_CANCELLED = "cancelled"
BLANK_STATUSES = (BLANK_STATUS_FREE, BLANK_STATUS_ISSUED, BLANK_STATUS_SPOILED, BLANK_STATUS_CANCELLED)

# Стартовый набор типов номерных бланков.
BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE = "driver_medical_certificate"
BLANK_TYPE_TRACTOR_MEDICAL_CERTIFICATE = "tractor_medical_certificate"
BLANK_TYPE_GUARD_MEDICAL_CERTIFICATE = "guard_medical_certificate"
NUMBERED_BLANK_TYPES = (
    (
        BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
        "Медицинское заключение для водительского удостоверения",
    ),
    (
        BLANK_TYPE_TRACTOR_MEDICAL_CERTIFICATE,
        "Справка для управления самоходными машинами",
    ),
    (
        BLANK_TYPE_GUARD_MEDICAL_CERTIFICATE,
        "Справка 002 ЧОД (для охраны)",
    ),
)


class BlankType(TimestampMixin, Base):
    """Справочник типов номерных бланков."""

    __tablename__ = "blank_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class BlankBatch(TimestampMixin, Base):
    """Партия номерных бланков, поступившая в центр."""

    __tablename__ = "blank_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int | None] = mapped_column(ForeignKey("centers.id"), nullable=True, index=True)
    blank_type: Mapped[str] = mapped_column(String(80), index=True)
    series: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    number_from: Mapped[int] = mapped_column(Integer)
    number_to: Mapped[int] = mapped_column(Integer)
    number_width: Mapped[int] = mapped_column(Integer, default=6)
    quantity: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BlankForm(TimestampMixin, Base):
    """Конкретный номерной бланк."""

    __tablename__ = "blank_forms"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("blank_batches.id"), index=True)
    center_id: Mapped[int | None] = mapped_column(ForeignKey("centers.id"), nullable=True, index=True)
    blank_type: Mapped[str] = mapped_column(String(80), index=True)
    series: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    number_value: Mapped[int] = mapped_column(Integer, index=True)
    full_number: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(20), default=BLANK_STATUS_FREE, index=True)

    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id"), nullable=True, index=True)
    client_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("client_documents.id"), nullable=True, index=True
    )
    generated_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_documents.id"), nullable=True, index=True
    )

    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    spoiled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    spoiled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    spoiled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "center_id", "blank_type", "full_number", name="uq_blank_forms_center_type_number"
        ),
        Index("ix_blank_forms_pick", "blank_type", "center_id", "status", "number_value"),
    )
