"""added_origin_store_and_dynamic_trip_structure

Revision ID: 4cb5982e02c4
Revises: dcfbf1b59317
Create Date: 2026-02-28 15:40:26.212875
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "4cb5982e02c4"
down_revision: Union[str, Sequence[str], None] = "dcfbf1b59317"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ===============================
    # MODIFY tpc_trip_stops
    # ===============================

    # Allow store_id to be nullable (for unknown locations)
    op.alter_column(
        "tpc_trip_stops", "store_id", existing_type=mysql.INTEGER(), nullable=True
    )

    # Make requires_review NOT NULL with default 0
    op.alter_column(
        "tpc_trip_stops",
        "requires_review",
        existing_type=mysql.TINYINT(display_width=1),
        nullable=False,
        server_default=sa.text("0"),
    )

    # Replace FK to use SET NULL instead of CASCADE
    op.drop_constraint(
        op.f("tpc_trip_stops_ibfk_1"), "tpc_trip_stops", type_="foreignkey"
    )

    op.create_foreign_key(
        "fk_trip_stops_store_id",
        "tpc_trip_stops",
        "tpc_stores",
        ["store_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Remove obsolete columns for dynamic stops
    op.drop_column("tpc_trip_stops", "stop_order")
    op.drop_column("tpc_trip_stops", "gps_valid_out")
    op.drop_column("tpc_trip_stops", "gps_valid_in")

    # ===============================
    # MODIFY tpc_trips
    # ===============================

    # Add origin_store_id for start/end validation
    op.add_column(
        "tpc_trips", sa.Column("origin_store_id", sa.Integer(), nullable=True)
    )

    op.create_foreign_key(
        "fk_trips_origin_store_id",
        "tpc_trips",
        "tpc_stores",
        ["origin_store_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""

    # ===============================
    # REVERT tpc_trips
    # ===============================

    op.drop_constraint("fk_trips_origin_store_id", "tpc_trips", type_="foreignkey")

    op.drop_column("tpc_trips", "origin_store_id")

    # ===============================
    # REVERT tpc_trip_stops
    # ===============================

    op.add_column(
        "tpc_trip_stops", sa.Column("stop_order", mysql.INTEGER(), nullable=False)
    )

    op.add_column(
        "tpc_trip_stops",
        sa.Column(
            "gps_valid_in",
            mysql.TINYINT(display_width=1),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )

    op.add_column(
        "tpc_trip_stops",
        sa.Column(
            "gps_valid_out",
            mysql.TINYINT(display_width=1),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )

    op.drop_constraint("fk_trip_stops_store_id", "tpc_trip_stops", type_="foreignkey")

    op.create_foreign_key(
        op.f("tpc_trip_stops_ibfk_1"),
        "tpc_trip_stops",
        "tpc_stores",
        ["store_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.alter_column(
        "tpc_trip_stops",
        "requires_review",
        existing_type=mysql.TINYINT(display_width=1),
        nullable=False,
        server_default=sa.text("0"),
    )

    op.alter_column(
        "tpc_trip_stops", "store_id", existing_type=mysql.INTEGER(), nullable=False
    )
