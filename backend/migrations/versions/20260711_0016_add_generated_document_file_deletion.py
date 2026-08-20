"""Add generated document file deletion metadata.

Revision ID: 20260711_0016
Revises: 20260709_0015
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260711_0016"
down_revision: str | None = "20260709_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("generated_documents"):
        return

    columns = {column["name"] for column in inspector.get_columns("generated_documents")}
    if "file_deleted_at" not in columns:
        op.add_column("generated_documents", sa.Column("file_deleted_at", sa.DateTime(timezone=True), nullable=True))
    if "file_delete_reason" not in columns:
        op.add_column("generated_documents", sa.Column("file_delete_reason", sa.String(length=500), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("generated_documents"):
        return

    columns = {column["name"] for column in inspector.get_columns("generated_documents")}
    if "file_delete_reason" in columns:
        op.drop_column("generated_documents", "file_delete_reason")
    if "file_deleted_at" in columns:
        op.drop_column("generated_documents", "file_deleted_at")
