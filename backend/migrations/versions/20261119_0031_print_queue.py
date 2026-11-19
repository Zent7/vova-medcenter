"""Очередь тихой печати: печатные агенты на рабочих местах и задания печати.

Revision ID: 20261119_0031
Revises: 20261107_0030
Create Date: 2026-11-19

print_agents — по одному агенту на рабочее место; в базе хранится только sha256 его токена.
print_jobs — задание печати готового документа: агент забирает его, печатает и сообщает результат.
Только новые таблицы: существующие данные не меняются. Откат удаляет обе таблицы вместе с заданиями.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261119_0031"
down_revision: str | None = "20261107_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_index_if_missing(name: str, table: str, column: str) -> None:
    # Первая миграция на пустой базе создает таблицы вместе с индексами по текущим моделям.
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, [column])


def upgrade() -> None:
    # Первая миграция (Base.metadata.create_all) на пустой базе уже создает эти таблицы по текущим моделям.
    # Поэтому каждую таблицу создаем только при отсутствии: иначе чистая база не поднимается.
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "print_agents" not in tables:
        op.create_table(
            "print_agents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("center_id", sa.Integer(), sa.ForeignKey("centers.id"), nullable=True),
            sa.Column("printer_name", sa.String(length=255), nullable=True),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("token_hash", name="uq_print_agents_token_hash"),
        )
    _create_index_if_missing("ix_print_agents_center_id", "print_agents", "center_id")

    if "print_jobs" not in tables:
        op.create_table(
            "print_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("generated_document_id", sa.Integer(), sa.ForeignKey("generated_documents.id"), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("center_id", sa.Integer(), sa.ForeignKey("centers.id"), nullable=True),
            sa.Column("copies", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("requested_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("agent_id", sa.Integer(), sa.ForeignKey("print_agents.id"), nullable=True),
            sa.Column("error", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )
    _create_index_if_missing("ix_print_jobs_generated_document_id", "print_jobs", "generated_document_id")
    _create_index_if_missing("ix_print_jobs_center_id", "print_jobs", "center_id")
    _create_index_if_missing("ix_print_jobs_status", "print_jobs", "status")
    _create_index_if_missing("ix_print_jobs_agent_id", "print_jobs", "agent_id")


def downgrade() -> None:
    op.drop_index("ix_print_jobs_agent_id", table_name="print_jobs")
    op.drop_index("ix_print_jobs_status", table_name="print_jobs")
    op.drop_index("ix_print_jobs_center_id", table_name="print_jobs")
    op.drop_index("ix_print_jobs_generated_document_id", table_name="print_jobs")
    op.drop_table("print_jobs")
    op.drop_index("ix_print_agents_center_id", table_name="print_agents")
    op.drop_table("print_agents")
