"""Expand encounter service notes for stored service details.

Revision ID: 20260612_0013
Revises: 20260601_0012
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260612_0013"
down_revision: str | None = "20260601_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return

    op.alter_column(
        "encounter_services",
        "notes",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return

    op.alter_column(
        "encounter_services",
        "notes",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
