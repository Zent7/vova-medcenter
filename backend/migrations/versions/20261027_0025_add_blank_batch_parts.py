"""Split a blank batch into packs that each operator takes separately.

A batch («партия») received by the center can be cut into packs («пачки»): consecutive
number ranges, one pack per operator. A blank belongs to at most one pack, and a batch
without packs keeps its old behaviour (``blank_forms.batch_part_id`` stays NULL).

Revision ID: 20261027_0025
Revises: 20261007_0024
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261027_0025"
down_revision: str | None = "20261007_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blank_batch_parts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("blank_batches.id"), nullable=False),
        sa.Column("part_no", sa.Integer(), nullable=False),
        sa.Column("number_from", sa.Integer(), nullable=False),
        sa.Column("number_to", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("batch_id", "part_no", name="uq_blank_batch_parts_batch_no"),
    )
    op.create_index("ix_blank_batch_parts_batch_id", "blank_batch_parts", ["batch_id"])
    op.add_column(
        "blank_forms",
        sa.Column("batch_part_id", sa.Integer(), sa.ForeignKey("blank_batch_parts.id"), nullable=True),
    )
    op.create_index("ix_blank_forms_batch_part_id", "blank_forms", ["batch_part_id"])


def downgrade() -> None:
    op.drop_index("ix_blank_forms_batch_part_id", table_name="blank_forms")
    op.drop_column("blank_forms", "batch_part_id")
    op.drop_index("ix_blank_batch_parts_batch_id", table_name="blank_batch_parts")
    op.drop_table("blank_batch_parts")
