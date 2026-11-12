"""fleet status on vehicle units + status log (Fleet operations view)

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-11-12

Units with an open "in repair" maintenance record start as "maintenance";
every other unit starts "available" (inactive units: "retired").
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_vehicle_units", sa.Column("fleet_status", sa.String(20), nullable=False, server_default="available"))
    op.add_column("tpc_vehicle_units", sa.Column("status_reason", sa.Text(), nullable=True))
    op.add_column("tpc_vehicle_units", sa.Column("status_since", sa.DateTime(), nullable=True))
    op.add_column("tpc_vehicle_units", sa.Column("status_until", sa.Date(), nullable=True))
    op.add_column("tpc_vehicle_units", sa.Column("status_updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_vehicle_units_status_updated_by", "tpc_vehicle_units", "tpc_users", ["status_updated_by"], ["id"])

    op.create_table(
        "tpc_vehicle_status_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehicle_unit_id", sa.Integer(), sa.ForeignKey("tpc_vehicle_units.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
    )
    op.create_index("ix_tpc_vehicle_status_logs_vehicle_unit_id", "tpc_vehicle_status_logs", ["vehicle_unit_id"])

    bind = op.get_bind()
    now = datetime.utcnow()
    bind.execute(sa.text(
        "UPDATE tpc_vehicle_units SET fleet_status = 'retired', status_since = :now "
        "WHERE is_active = 0"
    ), {"now": now})
    bind.execute(sa.text(
        "UPDATE tpc_vehicle_units u SET fleet_status = 'maintenance', status_since = :now, "
        "status_reason = 'Open repair record' "
        "WHERE u.is_active = 1 AND EXISTS (SELECT 1 FROM tpc_vehicle_maintenance m "
        "WHERE m.vehicle_unit_id = u.id AND m.in_repair = 1)"
    ), {"now": now})
    bind.execute(sa.text(
        "INSERT INTO tpc_vehicle_status_logs (vehicle_unit_id, status, reason, started_at) "
        "SELECT id, fleet_status, status_reason, :now FROM tpc_vehicle_units "
        "WHERE fleet_status <> 'available'"
    ), {"now": now})


def downgrade():
    op.drop_index("ix_tpc_vehicle_status_logs_vehicle_unit_id", table_name="tpc_vehicle_status_logs")
    op.drop_table("tpc_vehicle_status_logs")
    op.drop_constraint("fk_vehicle_units_status_updated_by", "tpc_vehicle_units", type_="foreignkey")
    for col in ("status_updated_by", "status_until", "status_since", "status_reason", "fleet_status"):
        op.drop_column("tpc_vehicle_units", col)
