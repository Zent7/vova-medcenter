"""Per-center work schedules: a schedule and its days belong to one medical center.

Revision ID: 20261107_0030
Revises: 20261106_0029
Create Date: 2026-11-07

The schedule used to be one per account (users.schedule_*). It moves to staff_center_schedules,
one row per (employee, center), and every staff_schedule_days row gets the center it is written in.
Existing data is kept: the old account schedule becomes the schedule of the account's main center,
and existing days belong to the main center too. Schedules in the account's other centers start
empty and are set in the staff form.

The downgrade restores the account schedule from the main-center row and drops days of the other
centers, because the old schema allows one day per employee.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261107_0030"
down_revision: str | None = "20261106_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SCHEDULES = "staff_center_schedules"
DAYS = "staff_schedule_days"
OLD_DAYS_UNIQUE = "uq_staff_schedule_days_user_date"
NEW_DAYS_UNIQUE = "uq_staff_schedule_days_user_center_date"
LEGACY_USER_COLUMNS = ("schedule_pattern", "schedule_start", "schedule_end", "schedule_anchor_date")


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_inspector().get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table)}


def _unique_names(table: str) -> dict[tuple[str, ...], str]:
    return {
        tuple(item["column_names"]): item["name"]
        for item in _inspector().get_unique_constraints(table)
        if item.get("name")
    }


def upgrade() -> None:
    # The initial migration builds every table from the current models, so a fresh database may
    # already have the new table, the column and the constraint. Create only what is missing.
    if SCHEDULES not in _tables():
        op.create_table(
            SCHEDULES,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("center_id", sa.Integer(), sa.ForeignKey("centers.id"), nullable=False),
            sa.Column("schedule_pattern", sa.String(length=10), nullable=False),
            sa.Column("schedule_start", sa.Time(), nullable=False),
            sa.Column("schedule_end", sa.Time(), nullable=False),
            sa.Column("schedule_anchor_date", sa.Date(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "center_id", name="uq_staff_center_schedules_user_center"),
        )
        op.create_index("ix_staff_center_schedules_user_id", SCHEDULES, ["user_id"])
        op.create_index("ix_staff_center_schedules_center_id", SCHEDULES, ["center_id"])

    if "center_id" not in _columns(DAYS):
        op.add_column(DAYS, sa.Column("center_id", sa.Integer(), sa.ForeignKey("centers.id"), nullable=True))
        op.create_index("ix_staff_schedule_days_center_id", DAYS, ["center_id"])

    user_columns = _columns("users")
    if "schedule_pattern" in user_columns:
        op.execute(
            sa.text(
                """
                INSERT INTO staff_center_schedules
                    (user_id, center_id, schedule_pattern, schedule_start, schedule_end, schedule_anchor_date,
                     created_at, updated_at)
                SELECT u.id, u.center_id, u.schedule_pattern, u.schedule_start, u.schedule_end,
                       u.schedule_anchor_date, now(), now()
                FROM users AS u
                WHERE u.schedule_pattern IS NOT NULL
                  AND u.schedule_start IS NOT NULL
                  AND u.schedule_end IS NOT NULL
                  AND u.center_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM staff_center_schedules AS s
                      WHERE s.user_id = u.id AND s.center_id = u.center_id
                  )
                """
            )
        )

    # Старые дни принадлежат основному медцентру учетки: одна запись на день была одна.
    op.execute(
        sa.text(
            """
            UPDATE staff_schedule_days AS d SET center_id = u.center_id
            FROM users AS u
            WHERE u.id = d.user_id AND d.center_id IS NULL
            """
        )
    )

    constraints = _unique_names(DAYS)
    if (("user_id", "work_date")) in constraints:
        op.drop_constraint(constraints[("user_id", "work_date")], DAYS, type_="unique")
    if NEW_DAYS_UNIQUE not in constraints.values():
        op.create_unique_constraint(NEW_DAYS_UNIQUE, DAYS, ["user_id", "center_id", "work_date"])

    for column in LEGACY_USER_COLUMNS:
        if column in user_columns:
            op.drop_column("users", column)


def downgrade() -> None:
    if "schedule_pattern" not in _columns("users"):
        op.add_column("users", sa.Column("schedule_pattern", sa.String(length=10), nullable=True))
        op.add_column("users", sa.Column("schedule_start", sa.Time(), nullable=True))
        op.add_column("users", sa.Column("schedule_end", sa.Time(), nullable=True))
        op.add_column("users", sa.Column("schedule_anchor_date", sa.Date(), nullable=True))

    if SCHEDULES in _tables():
        op.execute(
            sa.text(
                """
                UPDATE users AS u
                SET schedule_pattern = s.schedule_pattern,
                    schedule_start = s.schedule_start,
                    schedule_end = s.schedule_end,
                    schedule_anchor_date = s.schedule_anchor_date
                FROM staff_center_schedules AS s
                WHERE s.user_id = u.id AND s.center_id = u.center_id
                """
            )
        )

    # Старая схема помнит один день на учетку: дни других медцентров при откате удаляются.
    op.execute(
        sa.text(
            """
            DELETE FROM staff_schedule_days AS d
            USING users AS u
            WHERE u.id = d.user_id AND d.center_id IS DISTINCT FROM u.center_id
            """
        )
    )

    constraints = _unique_names(DAYS)
    if ("user_id", "center_id", "work_date") in constraints:
        op.drop_constraint(constraints[("user_id", "center_id", "work_date")], DAYS, type_="unique")
    if (("user_id", "work_date")) not in constraints:
        op.create_unique_constraint(OLD_DAYS_UNIQUE, DAYS, ["user_id", "work_date"])

    if "center_id" in _columns(DAYS):
        op.drop_column(DAYS, "center_id")
    if SCHEDULES in _tables():
        op.drop_table(SCHEDULES)
