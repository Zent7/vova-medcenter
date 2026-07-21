"""Add GIMS and LMK numbered blank types.

Revision ID: 20260721_0017
Revises: 20260711_0016
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260721_0017"
down_revision: str | None = "20260711_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DRIVER_TYPE = "driver_medical_certificate"
GIMS_TYPE = "gims_medical_certificate"
LMK_TYPE = "lmk_medical_certificate"

BLANK_TYPES = (
    (DRIVER_TYPE, "Водительская"),
    (GIMS_TYPE, "ГИМС"),
    ("tractor_medical_certificate", "Тракторная"),
    ("guard_medical_certificate", "Охранная"),
    (LMK_TYPE, "ЛМК"),
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
            """
        ).bindparams(blank_type=blank_type)
    )


def _reclassify_numbered_rows(table_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET blank_type = CASE
                WHEN coalesce(series, '') LIKE 'ЛМК%'
                    OR lower(coalesce(series, '')) LIKE 'лмк%'
                    OR lower(coalesce(series, '')) LIKE 'lmk%'
                    THEN :lmk_type
                WHEN coalesce(series, '') LIKE 'ГИМС%'
                    OR lower(coalesce(series, '')) LIKE 'гимс%'
                    OR lower(coalesce(series, '')) LIKE 'gims%'
                    THEN :gims_type
                ELSE blank_type
            END
            WHERE blank_type = :driver_type
              AND (
                coalesce(series, '') LIKE 'ЛМК%'
                OR lower(coalesce(series, '')) LIKE 'лмк%'
                OR lower(coalesce(series, '')) LIKE 'lmk%'
                OR coalesce(series, '') LIKE 'ГИМС%'
                OR lower(coalesce(series, '')) LIKE 'гимс%'
                OR lower(coalesce(series, '')) LIKE 'gims%'
              )
            """
        ).bindparams(driver_type=DRIVER_TYPE, gims_type=GIMS_TYPE, lmk_type=LMK_TYPE)
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if inspector.has_table("blank_types"):
        for code, name in BLANK_TYPES:
            _upsert_blank_type(code, name)

    if inspector.has_table("document_templates"):
        _mark_templates(
            GIMS_TYPE,
            """
            lower(coalesce(name, '')) LIKE '%гимс%'
            OR lower(coalesce(file_name, '')) LIKE '%гимс%'
            OR lower(coalesce(code, '')) LIKE '%gims%'
            """,
        )
        _mark_templates(
            LMK_TYPE,
            """
            lower(coalesce(name, '')) LIKE '%лмк%'
            OR lower(coalesce(file_name, '')) LIKE '%лмк%'
            OR lower(coalesce(code, '')) LIKE '%lmk%'
            """,
        )

    if inspector.has_table("blank_batches"):
        _reclassify_numbered_rows("blank_batches")
    if inspector.has_table("blank_forms"):
        _reclassify_numbered_rows("blank_forms")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if inspector.has_table("document_templates"):
        op.execute(
            sa.text(
                """
                UPDATE document_templates
                SET blank_type = :driver_type
                WHERE blank_type IN (:gims_type, :lmk_type)
                """
            ).bindparams(driver_type=DRIVER_TYPE, gims_type=GIMS_TYPE, lmk_type=LMK_TYPE)
        )

    for table_name in ("blank_forms", "blank_batches"):
        if inspector.has_table(table_name):
            op.execute(
                sa.text(
                    f"""
                    UPDATE {table_name}
                    SET blank_type = :driver_type
                    WHERE blank_type IN (:gims_type, :lmk_type)
                    """
                ).bindparams(driver_type=DRIVER_TYPE, gims_type=GIMS_TYPE, lmk_type=LMK_TYPE)
            )

    if inspector.has_table("blank_types"):
        op.execute(
            sa.text(
                """
                DELETE FROM blank_types
                WHERE code IN (:gims_type, :lmk_type)
                """
            ).bindparams(gims_type=GIMS_TYPE, lmk_type=LMK_TYPE)
        )
