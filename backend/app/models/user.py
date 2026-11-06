from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String, Table, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import generate_session_epoch
from app.db.base import Base
from app.models.mixins import TimestampMixin

# Единственная роль, которая видит все медцентры и может переключаться между
# ними. Остальные сотрудники работают в своём центре (users.center_id) и, если
# админ дал доступ, ещё в дополнительных (user_extra_centers).
ALL_CENTERS_ROLE_CODE = "admin"

# Дополнительные центры сотрудника. Основной центр лежит в users.center_id и
# сюда не дублируется: без этой таблицы сотрудник работает в одном центре.
user_extra_centers = Table(
    "user_extra_centers",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("center_id", ForeignKey("centers.id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int | None] = mapped_column(ForeignKey("centers.id"), nullable=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    login: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_epoch: Mapped[str] = mapped_column(String(32), default=generate_session_epoch)
    # График смен задаётся при создании учетной записи; у сотрудника без графика все поля пустые.
    schedule_pattern: Mapped[str | None] = mapped_column(String(10), nullable=True)
    schedule_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    schedule_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    center: Mapped["Center | None"] = relationship("Center")
    extra_centers: Mapped[list["Center"]] = relationship(
        "Center", secondary=user_extra_centers, order_by="Center.id"
    )
    role: Mapped[Role] = relationship(Role)

    @property
    def sees_all_centers(self) -> bool:
        return self.role.code == ALL_CENTERS_ROLE_CODE

    @property
    def pinned_center_id(self) -> int | None:
        """Основной центр сотрудника: в нём он оказывается при входе; у админа его нет."""
        return None if self.sees_all_centers else self.center_id

    @property
    def pinned_center_name(self) -> str | None:
        if self.sees_all_centers or self.center is None:
            return None
        return self.center.name

    @property
    def work_centers(self) -> list["Center"]:
        """Центры, где сотрудник может работать: основной первым, затем остальные.

        У админа список пуст: он видит все центры и без перечня.
        """
        if self.sees_all_centers:
            return []
        centers = [self.center] if self.center is not None else []
        centers += [center for center in self.extra_centers if center.id != self.center_id]
        return centers

    @property
    def schedule(self) -> dict | None:
        """График сотрудника или None, если его не задали."""
        if self.schedule_pattern is None:
            return None
        return {
            "pattern": self.schedule_pattern,
            "shift_start": self.schedule_start,
            "shift_end": self.schedule_end,
            "hourly_rate": self.hourly_rate,
        }
