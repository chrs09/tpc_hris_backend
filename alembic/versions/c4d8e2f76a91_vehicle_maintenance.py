"""vehicle maintenance

Revision ID: c4d8e2f76a91
Revises: a2c7f9d13e6b
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d8e2f76a91"
down_revision: Union[str, Sequence[str], None] = "a2c7f9d13e6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tpc_vehicle_maintenance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vehicle_unit_id", sa.Integer(), nullable=False),
        sa.Column("maintenance_type", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("service_date", sa.DateTime(), nullable=False),
        sa.Column("next_due_date", sa.DateTime(), nullable=True),
        sa.Column("odometer_reading", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["vehicle_unit_id"], ["tpc_vehicle_units.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tpc_vehicle_maintenance_id"),
        "tpc_vehicle_maintenance",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tpc_vehicle_maintenance_vehicle_unit_id"),
        "tpc_vehicle_maintenance",
        ["vehicle_unit_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tpc_vehicle_maintenance_vehicle_unit_id"),
        table_name="tpc_vehicle_maintenance",
    )
    op.drop_index(
        op.f("ix_tpc_vehicle_maintenance_id"), table_name="tpc_vehicle_maintenance"
    )
    op.drop_table("tpc_vehicle_maintenance")
