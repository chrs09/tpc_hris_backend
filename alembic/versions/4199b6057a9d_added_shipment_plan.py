"""added shipment plan

Revision ID: 4199b6057a9d
Revises: 937150a4da8f
Create Date: 2026-07-09 13:47:50.748346

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '4199b6057a9d'
down_revision: Union[str, Sequence[str], None] = '937150a4da8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    dispatch_status_enum = sa.Enum(
        "DRAFT",
        "ASSIGNED",
        "COMPLETED",
        "CANCELLED",
        name="shipment_plan_status_enum",
    )

    dispatch_item_status_enum = sa.Enum(
        "ASSIGNED",
        "STARTED",
        "COMPLETED",
        "CANCELLED",
        name="shipment_item_status_enum",
    )

    dispatch_status_enum.create(op.get_bind(), checkfirst=True)
    dispatch_item_status_enum.create(op.get_bind(), checkfirst=True)

    # =====================================================
    # tpc_dispatches
    # =====================================================

    op.create_table(
        "tpc_dispatches",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),

        sa.Column(
            "plan_date",
            sa.Date(),
            nullable=False,
        ),

        sa.Column(
            "status",
            dispatch_status_enum,
            nullable=False,
            server_default="DRAFT",
        ),

        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("tpc_users.id"),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_tpc_dispatches_plan_date",
        "tpc_dispatches",
        ["plan_date"],
    )

    op.create_index(
        "ix_tpc_dispatches_created_by",
        "tpc_dispatches",
        ["created_by"],
    )

    # =====================================================
    # tpc_dispatch_items
    # =====================================================

    op.create_table(
        "tpc_dispatch_items",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),

        sa.Column(
            "dispatch_id",
            sa.Integer(),
            sa.ForeignKey(
                "tpc_dispatches.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),

        sa.Column(
            "shipment_no",
            sa.String(100),
            nullable=False,
        ),

        sa.Column(
            "dealer_name",
            sa.String(255),
            nullable=False,
        ),

        sa.Column(
            "hauler_name",
            sa.String(255),
            nullable=True,
        ),

        sa.Column(
            "driver_id",
            sa.Integer(),
            sa.ForeignKey("tpc_users.id"),
            nullable=False,
        ),

        sa.Column(
            "vehicle_unit_id",
            sa.Integer(),
            sa.ForeignKey("tpc_vehicle_units.id"),
            nullable=False,
        ),

        sa.Column(
            "trip_rate_profile_id",
            sa.Integer(),
            sa.ForeignKey("tpc_trip_rate_profiles.id"),
            nullable=False,
        ),

        sa.Column(
            "pallets",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "cases",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "status",
            dispatch_item_status_enum,
            nullable=False,
            server_default="ASSIGNED",
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_tpc_dispatch_items_dispatch",
        "tpc_dispatch_items",
        ["dispatch_id"],
    )

    op.create_index(
        "ix_tpc_dispatch_items_shipment_no",
        "tpc_dispatch_items",
        ["shipment_no"],
    )

    op.create_index(
        "ix_tpc_dispatch_items_driver",
        "tpc_dispatch_items",
        ["driver_id"],
    )

    op.create_index(
        "ix_tpc_dispatch_items_vehicle",
        "tpc_dispatch_items",
        ["vehicle_unit_id"],
    )

    op.create_index(
        "ix_tpc_dispatch_items_trip_profile",
        "tpc_dispatch_items",
        ["trip_rate_profile_id"],
    )


def downgrade() -> None:

    dispatch_status_enum = sa.Enum(
        "DRAFT",
        "ASSIGNED",
        "COMPLETED",
        "CANCELLED",
        name="shipment_plan_status_enum",
    )

    dispatch_item_status_enum = sa.Enum(
        "ASSIGNED",
        "STARTED",
        "COMPLETED",
        "CANCELLED",
        name="shipment_item_status_enum",
    )

    op.drop_index(
        "ix_tpc_dispatch_items_trip_profile",
        table_name="tpc_dispatch_items",
    )

    op.drop_index(
        "ix_tpc_dispatch_items_vehicle",
        table_name="tpc_dispatch_items",
    )

    op.drop_index(
        "ix_tpc_dispatch_items_driver",
        table_name="tpc_dispatch_items",
    )

    op.drop_index(
        "ix_tpc_dispatch_items_shipment_no",
        table_name="tpc_dispatch_items",
    )

    op.drop_index(
        "ix_tpc_dispatch_items_dispatch",
        table_name="tpc_dispatch_items",
    )

    op.drop_table(
        "tpc_dispatch_items",
    )

    op.drop_index(
        "ix_tpc_dispatches_created_by",
        table_name="tpc_dispatches",
    )

    op.drop_index(
        "ix_tpc_dispatches_plan_date",
        table_name="tpc_dispatches",
    )

    op.drop_table(
        "tpc_dispatches",
    )

    dispatch_item_status_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )

    dispatch_status_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )