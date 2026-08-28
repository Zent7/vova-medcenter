"""Add the per-user session epoch that backs the "sign everyone out" action.

Revision ID: 20260828_0020
Revises: 20260825_0019
Create Date: 2026-08-28
"""

from collections.abc import Sequence
from secrets import token_hex

import sqlalchemy as sa
from alembic import op


revision: str = "20260828_0020"
down_revision: str | None = "20260825_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "session_epoch" in columns:
        return

    op.add_column("users", sa.Column("session_epoch", sa.String(length=32), nullable=True))

    users_table = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("session_epoch", sa.String(length=32)),
    )
    user_ids = [row[0] for row in bind.execute(sa.select(users_table.c.id)).all()]
    for user_id in user_ids:
        bind.execute(
            sa.update(users_table).where(users_table.c.id == user_id).values(session_epoch=token_hex(16))
        )

    op.alter_column("users", "session_epoch", existing_type=sa.String(length=32), nullable=False)


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "session_epoch" in columns:
        op.drop_column("users", "session_epoch")
