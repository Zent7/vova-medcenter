"""Continue the paper LMK certificate numbering per medical center.

Revision ID: 20260823_0018
Revises: 20260813_0013
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260823_0018"
down_revision: str | None = "20260813_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("centers")}
    if "lmk_certificate_last_number" not in columns:
        op.add_column(
            "centers",
            sa.Column("lmk_certificate_last_number", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("centers")}
    if "lmk_certificate_last_number" in columns:
        op.drop_column("centers", "lmk_certificate_last_number")
