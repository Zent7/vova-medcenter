from datetime import date, time

from sqlalchemy import Date, ForeignKey, SmallInteger, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin

# Что стоит в клетке графика: смена с временем, отгул, больничный или отпуск.
SCHEDULE_DAY_KINDS = ("shift", "dayoff", "sick", "vacation")
# Откуда взята запись: рассчитана по шаблону сотрудника или введена вручную.
SCHEDULE_DAY_SOURCES = ("pattern", "manual")


class StaffScheduleDay(TimestampMixin, Base):
    """Запись графика сотрудника на один день.

    Смены по шаблону не хранятся заранее: их создает кнопка «Создать график» или
    «Назначить первую смену». Ручные правки, отгулы, больничные и отпуска живут тут же.
    """

    __tablename__ = "staff_schedule_days"
    __table_args__ = (UniqueConstraint("user_id", "work_date", name="uq_staff_schedule_days_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Без ON DELETE: учетку с графиком не стираем, как и учетку с записями в программе —
    # удаление отключит ее, а история смен и факта останется.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(12))
    # Плановое время смены; у отгула, больничного и отпуска пусто.
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    # Ручной факт; пусто — день считается по отметкам «На работу».
    fact_start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    fact_end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="manual")
    # Номер смены в цикле шаблона (1 — первая); задается при расчете по шаблону и не меняется.
    shift_no: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
