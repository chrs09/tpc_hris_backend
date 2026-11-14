"""fuel request: the unit fueled and why (when not the assigned unit)

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from alembic import op

revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None

FK_NAME = "fk_tpc_fuel_requests_vehicle_unit_id"
IX_NAME = "ix_tpc_fuel_requests_vehicle_unit_id"


def upgrade():
    op.add_column("tpc_fuel_requests", sa.Column("vehicle_unit_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        FK_NAME, "tpc_fuel_requests", "tpc_vehicle_units", ["vehicle_unit_id"], ["id"]
    )
    op.create_index(IX_NAME, "tpc_fuel_requests", ["vehicle_unit_id"])
    op.add_column("tpc_fuel_requests", sa.Column("unit_reason", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("tpc_fuel_requests", "unit_reason")
    op.drop_constraint(FK_NAME, "tpc_fuel_requests", type_="foreignkey")
    op.drop_index(IX_NAME, table_name="tpc_fuel_requests")
    op.drop_column("tpc_fuel_requests", "vehicle_unit_id")
