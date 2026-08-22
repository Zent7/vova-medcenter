"""Store the active doctor's full name on each doctor role.

Revision ID: 20260813_0013
Revises: 20260721_0017
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260813_0013"
down_revision: str | None = "20260721_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("doctor_roles", sa.Column("full_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("doctor_roles", "full_name")
