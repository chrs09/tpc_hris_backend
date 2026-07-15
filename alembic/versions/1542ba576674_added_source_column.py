"""added source column

Revision ID: 1542ba576674
Revises: 921187fa9cf8
Create Date: 2026-07-14 12:25:18.302685

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1542ba576674'
down_revision: Union[str, Sequence[str], None] = '921187fa9cf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add the new `source` column.
    #    server_default ensures existing rows are backfilled to "manual"
    #    (safe default since none of your existing rows came from the API sync yet).
    op.add_column(
        "tpc_holidays",
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default="manual",
        ),
    )

    # Drop the server_default after backfill so future inserts rely on the
    # application-level default instead of the DB default (optional but cleaner).
    op.alter_column("tpc_holidays", "source", server_default=None)

    # 2. Add the unique constraint to prevent duplicate holiday entries
    #    from the same source on the same date with the same name.
    op.create_unique_constraint(
        "uq_holiday_date_source_name",
        "tpc_holidays",
        ["holiday_date", "source", "holiday_name"],
    )


def downgrade() -> None:
    # Reverse order: drop constraint first, then the column.
    op.drop_constraint(
        "uq_holiday_date_source_name",
        "tpc_holidays",
        type_="unique",
    )
    op.drop_column("tpc_holidays", "source")