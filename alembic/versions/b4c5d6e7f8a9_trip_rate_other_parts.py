"""trip rates: an "other" part for Driver Next, Helper 1st and Helper Next

Same as Driver 1st's driver_other: each rate column stays the BASIC, and its
other is added to it when a trip is paid (app/services/trip_rates.py).

No payout changes: every other starts at 0 on categories. On rate rules
they're left blank, which keeps the category's (0).

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None

COLUMNS = ("driver_next_other", "helper_first_other", "helper_next_other")


def upgrade():
    for name in COLUMNS:
        op.add_column(
            "tpc_trip_rate_profiles",
            sa.Column(name, sa.Numeric(10, 2), nullable=False, server_default="0"),
        )
        op.add_column("tpc_trip_rate_rules", sa.Column(name, sa.Numeric(10, 2), nullable=True))


def downgrade():
    for name in COLUMNS:
        op.drop_column("tpc_trip_rate_rules", name)
        op.drop_column("tpc_trip_rate_profiles", name)
