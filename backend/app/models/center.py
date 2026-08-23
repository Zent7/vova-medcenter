from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Center(TimestampMixin, Base):
    __tablename__ = "centers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inn: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ogrn: Mapped[str | None] = mapped_column(String(30), nullable=True)
    license_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    license_date: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Последний номер справки ЛМК, выданный в этом медцентре до перехода на
    # программу: электронная нумерация продолжает бумажный журнал со следующего.
    lmk_certificate_last_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
