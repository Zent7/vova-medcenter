"""Store citizenship and country of arrival separately from the address."""

from alembic import op
import sqlalchemy as sa

revision = "20260913_0022"
down_revision = "20260903_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The initial migration creates tables from current model metadata.
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("clients")}
    for name in ("citizenship", "arrival_country"):
        if name not in existing:
            op.add_column("clients", sa.Column(name, sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "arrival_country")
    op.drop_column("clients", "citizenship")
