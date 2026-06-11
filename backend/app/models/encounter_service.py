from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EncounterService(Base):
    __tablename__ = "encounter_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    legacy_source_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True, index=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    quantity: Mapped[int] = mapped_column(default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    sequence_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
