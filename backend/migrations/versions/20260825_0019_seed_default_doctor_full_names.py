"""Seed default doctor full names.

Revision ID: 20260825_0019
Revises: 20260823_0018
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260825_0019"
down_revision: str | None = "20260823_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_DOCTOR_FULL_NAMES = {
    "therapist": "Казаков И.В.",
    "chairman": "Казаков И.В.",
    "psychiatrist": "Аносов И.Е.",
    "psychiatrist-narcologist": "Аносов И.Е.",
    "neurologist": "Казаков И.В.",
    "otolaryngologist": "Барсуков А.Ф.",
    "surgeon": "Конюк М.В.",
    "ophthalmologist": "Дадалина Т.В.",
    "dermatologist": "Мехдиева Н.Ш.К.",
    "dentist": "Шадрикова Ю.А.",
}


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("doctor_roles")
    }
    if "full_name" not in columns:
        return

    for code, full_name in DEFAULT_DOCTOR_FULL_NAMES.items():
        op.execute(
            sa.text(
                """
                UPDATE doctor_roles
                SET full_name = :full_name
                WHERE code = :code
                  AND (full_name IS NULL OR btrim(full_name) = '')
                """
            ).bindparams(code=code, full_name=full_name)
        )


def downgrade() -> None:
    pass
