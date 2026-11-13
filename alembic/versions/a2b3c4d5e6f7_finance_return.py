"""finance review: returned_from (Finance can also return a trip to the coordinator)

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tpc_trip_finance_reviews",
        sa.Column("returned_from", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tpc_trip_finance_reviews", "returned_from")
