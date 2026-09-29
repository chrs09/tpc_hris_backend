"""attendance geofence flags

Time in/out outside the allowed attendance area is no longer refused --
it's recorded and flagged for review. These columns keep the geofence
result for each side.

Revision ID: 7a3c91d2e4b5
Revises: 1e1b340f0c1b
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa


revision = "7a3c91d2e4b5"
down_revision = "1e1b340f0c1b"
branch_labels = None
depends_on = None


def upgrade():
    for side in ("time_in", "time_out"):
        op.add_column(
            "tpc_attendance_records",
            sa.Column(f"{side}_outside_geofence", sa.Boolean(), nullable=True),
        )
        op.add_column(
            "tpc_attendance_records",
            sa.Column(f"{side}_geofence_note", sa.String(255), nullable=True),
        )


def downgrade():
    for side in ("time_in", "time_out"):
        op.drop_column("tpc_attendance_records", f"{side}_geofence_note")
        op.drop_column("tpc_attendance_records", f"{side}_outside_geofence")
