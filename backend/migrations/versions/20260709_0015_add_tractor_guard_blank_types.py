"""Add tractor and guard numbered blank types.

Revision ID: 20260709_0015
Revises: 20260701_0014
Create Date: 2026-07-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260709_0015"
down_revision: str | None = "20260701_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BLANK_TYPES = (
    (
        "driver_medical_certificate",
        "Медицинское заключение для водительского удостоверения",
    ),
    (
        "tractor_medical_certificate",
        "Справка для управления самоходными машинами",
    ),
    (
        "guard_medical_certificate",
        "Справка 002 ЧОД (для охраны)",
    ),
)


def _upsert_blank_type(code: str, name: str) -> None:
    op.execute(
        sa.text(
            """
            UPDATE blank_types
            SET name = :name,
                is_active = TRUE
            WHERE code = :code
            """
        ).bindparams(code=code, name=name)
    )
    op.execute(
        sa.text(
            """
            INSERT INTO blank_types (code, name, is_active)
            SELECT :code, :name, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM blank_types WHERE code = :code
            )
            """
        ).bindparams(code=code, name=name)
    )


def _mark_templates(blank_type: str, predicate: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE document_templates
            SET requires_numbered_blank = TRUE,
                blank_type = :blank_type
            WHERE ({predicate})
            AND (
                coalesce(requires_numbered_blank, FALSE) = FALSE
                OR blank_type IS NULL
                OR blank_type = ''
            )
            """
        ).bindparams(blank_type=blank_type)
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if inspector.has_table("blank_types"):
        for code, name in BLANK_TYPES:
            _upsert_blank_type(code, name)

    if not inspector.has_table("document_templates"):
        return

    _mark_templates(
        "tractor_medical_certificate",
        """
        lower(coalesce(name, '')) LIKE '%трактор%'
        OR lower(coalesce(file_name, '')) LIKE '%трактор%'
        OR lower(coalesce(code, '')) LIKE '%tractor%'
        OR lower(coalesce(name, '')) LIKE '%tractor%'
        OR lower(coalesce(file_name, '')) LIKE '%tractor%'
        OR lower(coalesce(name, '')) LIKE '%071%'
        OR lower(coalesce(file_name, '')) LIKE '%071%'
        """,
    )
    _mark_templates(
        "guard_medical_certificate",
        """
        lower(coalesce(name, '')) LIKE '%охран%'
        OR lower(coalesce(file_name, '')) LIKE '%охран%'
        OR lower(coalesce(code, '')) LIKE '%guard%'
        OR lower(coalesce(name, '')) LIKE '%guard%'
        OR lower(coalesce(file_name, '')) LIKE '%guard%'
        OR lower(coalesce(name, '')) LIKE '%чод%'
        OR lower(coalesce(file_name, '')) LIKE '%чод%'
        OR lower(coalesce(name, '')) LIKE '%002%'
        OR lower(coalesce(file_name, '')) LIKE '%002%'
        """,
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if inspector.has_table("document_templates"):
        op.execute(
            sa.text(
                """
                UPDATE document_templates
                SET requires_numbered_blank = FALSE,
                    blank_type = NULL
                WHERE blank_type IN (
                    'tractor_medical_certificate',
                    'guard_medical_certificate'
                )
                """
            )
        )

    if inspector.has_table("blank_types"):
        op.execute(
            sa.text(
                """
                DELETE FROM blank_types
                WHERE code IN (
                    'tractor_medical_certificate',
                    'guard_medical_certificate'
                )
                """
            )
        )
