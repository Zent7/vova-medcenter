from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class CenterDoctorName(TimestampMixin, Base):
    """ФИО врача конкретной специальности в конкретном медцентре.

    Список специальностей (`doctor_roles`) общий: терапевт остаётся терапевтом в
    любом медцентре. А человек, который её занимает, у каждого центра свой,
    поэтому ФИО хранится здесь, а не в `doctor_roles.full_name`.
    """

    __tablename__ = "center_doctor_names"

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id"), index=True)
    # Код роли, а не внешний ключ: `DoctorExam.doctor_role_id` тоже хранит код,
    # и осмотры связываются со справочником именно по нему.
    doctor_role_code: Mapped[str] = mapped_column(String(80), index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("center_id", "doctor_role_code", name="uq_center_doctor_names_center_role"),
    )
