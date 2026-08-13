from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ServiceCategory(Base):
    __tablename__ = "service_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(default=100)


class Service(TimestampMixin, Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    legacy_source_id: Mapped[int | None] = mapped_column(nullable=True, unique=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("service_categories.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_sequence: Mapped[bool] = mapped_column(Boolean, default=False)
    recall_after_days: Mapped[int | None] = mapped_column(nullable=True)


class DoctorRole(Base):
    __tablename__ = "doctor_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ServiceDoctorRole(Base):
    __tablename__ = "service_doctor_roles"

    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), primary_key=True)
    doctor_role_id: Mapped[int] = mapped_column(ForeignKey("doctor_roles.id"), primary_key=True)
