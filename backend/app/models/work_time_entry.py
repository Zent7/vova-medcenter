from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class WorkTimeEntry(TimestampMixin, Base):
    """Отметка «На работу» — «С работы»: пока ended_at пуст, сотрудник на работе.

    Время хранится с часовым поясом; по дням его делит сервис статуса по местному времени.
    """

    __tablename__ = "work_time_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Без ON DELETE: как график, учетку с отметками не стираем — удаление только отключит ее.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
