"""add coordinator role

Revision ID: 00de30e36f68
Revises: c5af81c5f70d
Create Date: 2026-09-15 08:23:10.717962

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00de30e36f68'
down_revision: Union[str, Sequence[str], None] = 'c5af81c5f70d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "tpc_users"
COLUMN_NAME = "role"

OLD_VALUES = [
    "SUPERADMIN",
    "ADMIN",
    "DRIVER",
    "HELPER",
    "EMPLOYEE",
    "COORDINATOR_ADMIN",
    "PAYROLL_ADMIN",
    "OFFICE_ADMIN",
]

# Narrower than COORDINATOR_ADMIN -- trip assignment/dispatch only (see
# "Trip Assignment", the renamed Start Trip Bypass page).
ADDED_VALUES = ["COORDINATOR"]

NEW_VALUES = OLD_VALUES + ADDED_VALUES

DEFAULT_VALUE = "EMPLOYEE"


def _enum_sql(values: list[str]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"ENUM({quoted})"


def upgrade() -> None:
    # MySQL has no ALTER TYPE / ADD VALUE like Postgres -- widening a
    # native ENUM(...) column means redefining it with the full new set
    # of values (same pattern as 1b771e824088_added_new_rol_for_...).
    op.execute(
        f"ALTER TABLE {TABLE_NAME} "
        f"MODIFY COLUMN {COLUMN_NAME} {_enum_sql(NEW_VALUES)} "
        f"NOT NULL DEFAULT '{DEFAULT_VALUE}'"
    )


def downgrade() -> None:
    connection = op.get_bind()

    placeholders = ", ".join(f"'{v}'" for v in ADDED_VALUES)
    in_use = connection.execute(
        sa.text(
            f"SELECT username, {COLUMN_NAME} FROM {TABLE_NAME} "
            f"WHERE {COLUMN_NAME} IN ({placeholders})"
        )
    ).fetchall()

    if in_use:
        usernames = ", ".join(f"{row.username} ({row[1]})" for row in in_use)
        raise RuntimeError(
            "Cannot downgrade: the following users still have a role "
            f"being removed by this migration: {usernames}. "
            "Reassign them to an existing role before downgrading."
        )

    op.execute(
        f"ALTER TABLE {TABLE_NAME} "
        f"MODIFY COLUMN {COLUMN_NAME} {_enum_sql(OLD_VALUES)} "
        f"NOT NULL DEFAULT '{DEFAULT_VALUE}'"
    )
