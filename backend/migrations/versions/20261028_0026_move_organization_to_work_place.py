"""Перенести «Организацию» в «Место работы», где рабочее место пустое.

В карточке клиента поля «Организация» больше нет, в документы печатается только
«Место работы». Клиенты, у которых место работы было записано только в «Организацию»,
сохраняют его в печати. Колонку organization не удаляем.

Revision ID: 20261028_0026
Revises: 20261027_0025
Create Date: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20261028_0026"
down_revision: str | None = "20261027_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE clients SET work_place = organization "
        "WHERE (work_place IS NULL OR work_place = '') "
        "AND organization IS NOT NULL AND organization <> ''"
    )


def downgrade() -> None:
    # Откат не делаем: место работы могли уже поправить вручную.
    pass
