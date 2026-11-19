from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PRINT_JOB_QUEUED = "queued"
PRINT_JOB_CLAIMED = "claimed"
PRINT_JOB_DONE = "done"
PRINT_JOB_FAILED = "failed"
PRINT_JOB_CANCELLED = "cancelled"


class PrintAgent(Base):
    """Печатный агент на рабочем месте: сам опрашивает сервер и печатает задания.

    Сервер ничего не открывает к компьютеру клиники: агент ходит наружу, поэтому
    браузер не обращается к localhost. Токен хранится только хешем sha256.
    center_id пустой — агент берет задания всех центров.
    """

    __tablename__ = "print_agents"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_print_agents_token_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    center_id: Mapped[int | None] = mapped_column(ForeignKey("centers.id"), nullable=True, index=True)
    printer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PrintJob(Base):
    """Задание печати готового документа. Файл берется из generated_documents при выдаче агенту."""

    __tablename__ = "print_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    generated_document_id: Mapped[int] = mapped_column(ForeignKey("generated_documents.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    center_id: Mapped[int | None] = mapped_column(ForeignKey("centers.id"), nullable=True, index=True)
    copies: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(20), index=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("print_agents.id"), nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
