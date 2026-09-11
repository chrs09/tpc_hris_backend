"""seven step trip flow

Revision ID: 414f9840c17e
Revises: b7c3d9e14f52
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "414f9840c17e"
down_revision: Union[str, Sequence[str], None] = "e5b8f2a9c1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Trip: current_step drives the mobile app's live action button,
    # separate from the coarse `status` enum used by office/finance
    # reporting. ticket_no becomes nullable -- a dispatched trip has no
    # shipment number until the driver's Checkout step fills it in.
    op.add_column(
        "tpc_trips",
        sa.Column(
            "current_step",
            sa.String(length=20),
            nullable=False,
            server_default="ASSIGNED",
        ),
    )
    op.add_column(
        "tpc_trips",
        sa.Column("destination_store_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_tpc_trips_destination_store_id",
        "tpc_trips",
        "tpc_stores",
        ["destination_store_id"],
        ["id"],
    )
    op.alter_column(
        "tpc_trips",
        "ticket_no",
        existing_type=sa.String(length=100),
        nullable=True,
    )

    # is_archived already existed on this table (added outside of a
    # tracked migration) with no DB default -- give it one so any insert
    # path that doesn't explicitly set it doesn't fail NOT NULL.
    op.execute(
        "ALTER TABLE tpc_trips MODIFY COLUMN is_archived TINYINT(1) NOT NULL DEFAULT 0"
    )

    # TripStop.status: CHECKED_OUT -> split into UNLOADING (Start
    # Unloading step) and DELIVERED (Delivered step, replaces the old
    # CHECKED_OUT terminal value).
    op.execute(
        """
        ALTER TABLE tpc_trip_stops
        MODIFY COLUMN status ENUM(
            'CHECKED_IN','UNLOADING','DELIVERED','CHECKED_OUT'
        ) NOT NULL
        """
    )
    op.execute(
        "UPDATE tpc_trip_stops SET status = 'DELIVERED' WHERE status = 'CHECKED_OUT'"
    )
    op.execute(
        """
        ALTER TABLE tpc_trip_stops
        MODIFY COLUMN status ENUM(
            'CHECKED_IN','UNLOADING','DELIVERED'
        ) NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE tpc_trip_stops
        MODIFY COLUMN status ENUM(
            'CHECKED_IN','UNLOADING','DELIVERED','CHECKED_OUT'
        ) NOT NULL
        """
    )
    op.execute(
        "UPDATE tpc_trip_stops SET status = 'CHECKED_OUT' WHERE status IN ('UNLOADING','DELIVERED')"
    )
    op.execute(
        """
        ALTER TABLE tpc_trip_stops
        MODIFY COLUMN status ENUM(
            'CHECKED_IN','CHECKED_OUT'
        ) NOT NULL
        """
    )

    op.alter_column(
        "tpc_trips",
        "ticket_no",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.drop_constraint(
        "fk_tpc_trips_destination_store_id", "tpc_trips", type_="foreignkey"
    )
    op.drop_column("tpc_trips", "destination_store_id")
    op.drop_column("tpc_trips", "current_step")
