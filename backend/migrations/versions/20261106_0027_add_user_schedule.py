"""Give a staff account its work schedule: shift pattern, hours and hourly rate.

Revision ID: 20261106_0027
Revises: 20261028_0026
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261106_0027"
down_revision: str | None = "20261028_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SCHEDULE_COLUMNS = ("schedule_pattern", "schedule_start", "schedule_end", "hourly_rate")


def _existing_user_columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}


def upgrade() -> None:
    # The initial migration builds tables from the current models, so a fresh database
    # may already have these columns. Add only the ones that are missing.
    existing = _existing_user_columns()
    if "schedule_pattern" not in existing:
        op.add_column("users", sa.Column("schedule_pattern", sa.String(length=10), nullable=True))
    if "schedule_start" not in existing:
        op.add_column("users", sa.Column("schedule_start", sa.Time(), nullable=True))
    if "schedule_end" not in existing:
        op.add_column("users", sa.Column("schedule_end", sa.Time(), nullable=True))
    if "hourly_rate" not in existing:
        op.add_column("users", sa.Column("hourly_rate", sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade() -> None:
    existing = _existing_user_columns()
    for name in reversed(SCHEDULE_COLUMNS):
        if name in existing:
            op.drop_column("users", name)
