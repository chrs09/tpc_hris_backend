"""trip rates: split Driver 1st into basic + allowance + other

driver_first_trip_rate now holds the BASIC on categories and rate rules;
driver_allowance and driver_other are added to it when a trip is paid
(app/services/trip_rates.py).

No payout changes:
- Categories at the known all-in rates are split: 565 -> 540 + 25, and
  782.50 -> 540 + 25 + 217.50. Any other rate stays all in the basic.
- Existing rules that set Driver 1st were all-in amounts, so they get
  allowance 0 and other 0 (otherwise they'd add the category's on top).

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_trip_rate_profiles",
        sa.Column("driver_allowance", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "tpc_trip_rate_profiles",
        sa.Column("driver_other", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.add_column("tpc_trip_rate_rules", sa.Column("driver_allowance", sa.Numeric(10, 2), nullable=True))
    op.add_column("tpc_trip_rate_rules", sa.Column("driver_other", sa.Numeric(10, 2), nullable=True))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE tpc_trip_rate_profiles "
            "SET driver_first_trip_rate = 540, driver_allowance = 25 "
            "WHERE driver_first_trip_rate = 565"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE tpc_trip_rate_profiles "
            "SET driver_first_trip_rate = 540, driver_allowance = 25, driver_other = 217.50 "
            "WHERE driver_first_trip_rate = 782.50"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE tpc_trip_rate_rules "
            "SET driver_allowance = 0, driver_other = 0 "
            "WHERE driver_first_trip_rate IS NOT NULL"
        )
    )


def downgrade():
    # Back to all-in amounts.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE tpc_trip_rate_profiles "
            "SET driver_first_trip_rate = driver_first_trip_rate + driver_allowance + driver_other"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE tpc_trip_rate_rules "
            "SET driver_first_trip_rate = driver_first_trip_rate "
            "+ COALESCE(driver_allowance, 0) + COALESCE(driver_other, 0) "
            "WHERE driver_first_trip_rate IS NOT NULL"
        )
    )
    op.drop_column("tpc_trip_rate_rules", "driver_other")
    op.drop_column("tpc_trip_rate_rules", "driver_allowance")
    op.drop_column("tpc_trip_rate_profiles", "driver_other")
    op.drop_column("tpc_trip_rate_profiles", "driver_allowance")
