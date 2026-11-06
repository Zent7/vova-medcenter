"""Work time marks: «На работу» and «С работы» per employee.

Revision ID: 20261106_0029
Revises: 20261106_0028
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261106_0029"
down_revision: str | None = "20261106_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE = "work_time_entries"
INDEX_NAME = "ix_work_time_entries_user_id"


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if TABLE in _existing_tables():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(INDEX_NAME, TABLE, ["user_id"])


def downgrade() -> None:
    if TABLE not in _existing_tables():
        return
    op.drop_index(INDEX_NAME, table_name=TABLE)
    op.drop_table(TABLE)
