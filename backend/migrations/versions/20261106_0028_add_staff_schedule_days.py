"""Monthly work schedule: per-day shifts, days off, sick leave, vacation and actual hours.

Revision ID: 20261106_0028
Revises: 20261106_0027
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261106_0028"
down_revision: str | None = "20261106_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE = "staff_schedule_days"
UNIQUE_NAME = "uq_staff_schedule_days_user_date"


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_user_columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}


def upgrade() -> None:
    # The initial migration builds tables from the current models, so a fresh database
    # may already have the table and the column. Create only what is missing.
    if "schedule_anchor_date" not in _existing_user_columns():
        op.add_column("users", sa.Column("schedule_anchor_date", sa.Date(), nullable=True))

    if TABLE not in _existing_tables():
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("work_date", sa.Date(), nullable=False),
            sa.Column("kind", sa.String(length=12), nullable=False),
            sa.Column("start_time", sa.Time(), nullable=True),
            sa.Column("end_time", sa.Time(), nullable=True),
            sa.Column("fact_start_time", sa.Time(), nullable=True),
            sa.Column("fact_end_time", sa.Time(), nullable=True),
            sa.Column("source", sa.String(length=10), nullable=False),
            sa.Column("shift_no", sa.SmallInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "work_date", name=UNIQUE_NAME),
        )
        op.create_index("ix_staff_schedule_days_user_id", TABLE, ["user_id"])
        op.create_index("ix_staff_schedule_days_work_date", TABLE, ["work_date"])


def downgrade() -> None:
    if TABLE in _existing_tables():
        op.drop_index("ix_staff_schedule_days_work_date", table_name=TABLE)
        op.drop_index("ix_staff_schedule_days_user_id", table_name=TABLE)
        op.drop_table(TABLE)
    if "schedule_anchor_date" in _existing_user_columns():
        op.drop_column("users", "schedule_anchor_date")
