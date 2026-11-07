from datetime import date, time

from sqlalchemy import Date, ForeignKey, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class StaffCenterSchedule(TimestampMixin, Base):
    """График сотрудника в одном медцентре: шаблон, время смены и первая смена цикла.

    У сотрудника с двумя медцентрами два графика: в каждом свой шаблон и свой цикл.
    Дни графика (смены, отгулы, факт) лежат в `staff_schedule_days` с тем же `center_id`.
    Ставка одна на учетную запись и живет в `users.hourly_rate`.
    """

    __tablename__ = "staff_center_schedules"
    __table_args__ = (UniqueConstraint("user_id", "center_id", name="uq_staff_center_schedules_user_center"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Удаление учетки без записей уводит и ее графики (ON DELETE CASCADE); с записями учетку не стирают.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id"), index=True)
    schedule_pattern: Mapped[str] = mapped_column(String(10))
    schedule_start: Mapped[time] = mapped_column(Time)
    schedule_end: Mapped[time] = mapped_column(Time)
    # Первая смена цикла: с этого дня график по шаблону считается без пропусков.
    schedule_anchor_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    center: Mapped["Center"] = relationship("Center", lazy="joined")

    @property
    def center_name(self) -> str:
        return self.center.name
