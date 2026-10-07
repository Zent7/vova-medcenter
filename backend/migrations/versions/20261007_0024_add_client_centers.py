"""Give every medical center its own client base.

Clients used to be shared by all centers: an encounter belonged to a center, the
client did not. The link table ``client_centers`` puts a client into one or
several centers. Existing clients are placed where they already have encounters;
a client without any encounter goes to the first working center (Мед-Авто), where
the customer's old program lived, so nothing that already works there disappears.

Revision ID: 20261007_0024
Revises: 20261005_0023
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261007_0024"
down_revision: str | None = "20261005_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_NAME = "client_centers"
DEFAULT_CENTER_CODE = "center-a"


def upgrade() -> None:
    bind = op.get_bind()
    # The initial migration creates tables from current model metadata, so a fresh
    # database already has this one (and has no clients to place).
    if sa.inspect(bind).has_table(TABLE_NAME):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("centers.id", ondelete="CASCADE"), primary_key=True),
    )

    bind.execute(
        sa.text(
            "INSERT INTO client_centers (client_id, center_id) "
            "SELECT DISTINCT client_id, center_id FROM encounters "
            "WHERE deleted_at IS NULL AND client_id IS NOT NULL AND center_id IS NOT NULL"
        )
    )
    default_center_id = bind.execute(
        sa.text("SELECT id FROM centers WHERE code = :code"), {"code": DEFAULT_CENTER_CODE}
    ).scalar()
    if default_center_id is None:
        default_center_id = bind.execute(sa.text("SELECT MIN(id) FROM centers")).scalar()
    if default_center_id is not None:
        bind.execute(
            sa.text(
                "INSERT INTO client_centers (client_id, center_id) "
                "SELECT clients.id, :center_id FROM clients "
                "WHERE NOT EXISTS (SELECT 1 FROM client_centers WHERE client_centers.client_id = clients.id)"
            ),
            {"center_id": default_center_id},
        )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(TABLE_NAME):
        op.drop_table(TABLE_NAME)
