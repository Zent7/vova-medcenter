"""Per-center doctor directory: the specialty is shared, the person is not.

Existing names live in `doctor_roles.full_name`, one row for the whole database,
so a second center could not hire its own doctors without renaming the first
center's. They move to the center that actually has the encounters — the oldest
one — and every other center starts with an empty directory of its own.

Revision ID: 20260903_0021
Revises: 20260828_0020
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260903_0021"
down_revision: str | None = "20260828_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_NAME = "center_doctor_names"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(TABLE_NAME):
        op.create_table(
            TABLE_NAME,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("center_id", sa.Integer(), sa.ForeignKey("centers.id"), nullable=False),
            sa.Column("doctor_role_code", sa.String(length=80), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("center_id", "doctor_role_code", name="uq_center_doctor_names_center_role"),
        )
        op.create_index(f"ix_{TABLE_NAME}_center_id", TABLE_NAME, ["center_id"])
        op.create_index(f"ix_{TABLE_NAME}_doctor_role_code", TABLE_NAME, ["doctor_role_code"])

    if "full_name" not in {column["name"] for column in inspector.get_columns("doctor_roles")}:
        return

    # Имена принадлежат тому центру, где реально велись приёмы. Обычно это самый
    # старый центр, но если его завели раньше, чем импортировали чужую базу,
    # обращений у него может не быть — тогда он бы забрал справочник себе, а
    # центр с историей остался бы пустым.
    home_center_id = None
    if inspector.has_table("encounters"):
        home_center_id = bind.execute(
            sa.text(
                "SELECT c.id FROM centers c "
                "WHERE EXISTS (SELECT 1 FROM encounters e WHERE e.center_id = c.id) "
                "ORDER BY c.id ASC LIMIT 1"
            )
        ).scalar()
    if home_center_id is None:
        home_center_id = bind.execute(sa.text("SELECT id FROM centers ORDER BY id ASC LIMIT 1")).scalar()
    if home_center_id is None:
        return

    existing_codes = {
        row[0]
        for row in bind.execute(
            sa.text(f"SELECT doctor_role_code FROM {TABLE_NAME} WHERE center_id = :center_id"),
            {"center_id": home_center_id},
        ).all()
    }
    rows = bind.execute(
        sa.text(
            "SELECT code, full_name FROM doctor_roles "
            "WHERE full_name IS NOT NULL AND TRIM(full_name) <> ''"
        )
    ).all()
    for code, full_name in rows:
        role_code = str(code or "").strip()
        if not role_code or role_code in existing_codes:
            continue
        bind.execute(
            sa.text(
                f"INSERT INTO {TABLE_NAME} (center_id, doctor_role_code, full_name) "
                "VALUES (:center_id, :doctor_role_code, :full_name)"
            ),
            {
                "center_id": home_center_id,
                "doctor_role_code": role_code,
                "full_name": str(full_name).strip(),
            },
        )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(TABLE_NAME):
        op.drop_table(TABLE_NAME)
