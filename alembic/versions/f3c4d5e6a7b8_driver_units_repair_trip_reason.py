"""vehicle units: assigned driver; maintenance: in repair (blocks
dispatch) with expected return; trips: urgent label and the reason a
driver used a unit other than their own

Revision ID: f3c4d5e6a7b8
Revises: e2b3c4d5f6a7
Create Date: 2026-10-14
"""

import sqlalchemy as sa
from alembic import op

revision = "f3c4d5e6a7b8"
down_revision = "e2b3c4d5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_vehicle_units",
        sa.Column("assigned_driver_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
    )
    op.create_unique_constraint(
        "uq_vehicle_units_assigned_driver", "tpc_vehicle_units", ["assigned_driver_id"]
    )

    op.add_column(
        "tpc_vehicle_maintenance",
        sa.Column("in_repair", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("tpc_vehicle_maintenance", sa.Column("expected_return_date", sa.DateTime(), nullable=True))
    op.add_column("tpc_vehicle_maintenance", sa.Column("repaired_at", sa.DateTime(), nullable=True))

    op.add_column(
        "tpc_trips",
        sa.Column("is_urgent", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("tpc_trips", sa.Column("unit_reason_type", sa.String(40), nullable=True))
    op.add_column("tpc_trips", sa.Column("unit_reason", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("tpc_trips", "unit_reason")
    op.drop_column("tpc_trips", "unit_reason_type")
    op.drop_column("tpc_trips", "is_urgent")
    op.drop_column("tpc_vehicle_maintenance", "repaired_at")
    op.drop_column("tpc_vehicle_maintenance", "expected_return_date")
    op.drop_column("tpc_vehicle_maintenance", "in_repair")
    op.drop_constraint("uq_vehicle_units_assigned_driver", "tpc_vehicle_units", type_="unique")
    op.drop_column("tpc_vehicle_units", "assigned_driver_id")
