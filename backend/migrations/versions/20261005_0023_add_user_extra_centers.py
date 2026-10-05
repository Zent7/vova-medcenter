"""Let a staff member work in several centers.

`users.center_id` stays the main center, the one a person opens at login. Extra
centers go to a link table, so every existing account keeps working in its one
center without any data move.

Revision ID: 20261005_0023
Revises: 20260913_0022
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261005_0023"
down_revision: str | None = "20260913_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_NAME = "user_extra_centers"


def upgrade() -> None:
    # The initial migration creates tables from current model metadata, so a fresh
    # database already has this one.
    if sa.inspect(op.get_bind()).has_table(TABLE_NAME):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("centers.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(TABLE_NAME):
        op.drop_table(TABLE_NAME)
