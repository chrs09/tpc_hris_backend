"""route rides: a driver riding along on another driver's trip (+ manual)

Paid like a driver trip of that category (Driver 1st / Next) -- no
separate rate.

Revision ID: d3a4b5c6e7f9
Revises: c2f3a4b5d6e7
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "d3a4b5c6e7f9"
down_revision = "c2f3a4b5d6e7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_route_rides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rider_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=False),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("tpc_trips.id"), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="assigned"),
        sa.Column("ride_date", sa.Date(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "trip_rate_profile_id",
            sa.Integer(),
            sa.ForeignKey("tpc_trip_rate_profiles.id"),
            nullable=True,
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tpc_route_rides_id", "tpc_route_rides", ["id"])
    op.create_index("ix_tpc_route_rides_rider_user_id", "tpc_route_rides", ["rider_user_id"])
    op.create_index("ix_tpc_route_rides_trip_id", "tpc_route_rides", ["trip_id"])
    op.create_index("ix_tpc_route_rides_ride_date", "tpc_route_rides", ["ride_date"])


def downgrade():
    # Dropping the table drops its indexes and foreign keys with it.
    op.drop_table("tpc_route_rides")
