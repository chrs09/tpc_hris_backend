"""added new rol for coordinator,payroll,office

Revision ID: 1b771e824088
Revises: 05e9da8f6f16
Create Date: 2026-07-28 17:19:52.576356

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b771e824088'
down_revision: Union[str, Sequence[str], None] = '05e9da8f6f16'
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
]

NEW_VALUES = OLD_VALUES + [
    "COORDINATOR_ADMIN",
    "PAYROLL_ADMIN",
    "OFFICE_ADMIN",
]

ADDED_VALUES = [
    "COORDINATOR_ADMIN",
    "PAYROLL_ADMIN",
    "OFFICE_ADMIN",
]

DEFAULT_VALUE = "EMPLOYEE"


def _enum_sql(values: list[str]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"ENUM({quoted})"


def upgrade() -> None:
    """Upgrade schema."""
    # MySQL has no ALTER TYPE / ADD VALUE like Postgres. A SQLAlchemy
    # Enum column on MySQL is a native ENUM(...) column, so widening it
    # means redefining the column with the full new set of values.
    op.execute(
        f"ALTER TABLE {TABLE_NAME} "
        f"MODIFY COLUMN {COLUMN_NAME} {_enum_sql(NEW_VALUES)} "
        f"NOT NULL DEFAULT '{DEFAULT_VALUE}'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Narrowing the ENUM back down. If any row still holds one of the
    # roles being removed, MODIFY COLUMN would either error (strict
    # sql_mode) or silently blank the value out (non-strict sql_mode) —
    # neither is what we want, so check first and refuse if any exist.
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