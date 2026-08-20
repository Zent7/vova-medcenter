"""Add suppressed doctor roles to encounters.

Revision ID: 20260701_0014
Revises: 20260612_0013
Create Date: 2026-07-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260701_0014"
down_revision: str | None = "20260612_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {col["name"] for col in inspector.get_columns("encounters")}

    if "suppressed_doctor_role_ids" not in columns:
        op.add_column(
            "encounters",
            sa.Column("suppressed_doctor_role_ids", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {col["name"] for col in inspector.get_columns("encounters")}

    if "suppressed_doctor_role_ids" in columns:
        op.drop_column("encounters", "suppressed_doctor_role_ids")
