"""trip corrections: requested changes to a finished trip, approved by Finance

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_trip_corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("tpc_trips.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested", sa.Text(), nullable=False),
        sa.Column("original", sa.Text(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
    )
    op.create_index("ix_tpc_trip_corrections_trip_id", "tpc_trip_corrections", ["trip_id"])
    op.create_index("ix_tpc_trip_corrections_status", "tpc_trip_corrections", ["status"])


def downgrade():
    op.drop_index("ix_tpc_trip_corrections_status", table_name="tpc_trip_corrections")
    op.drop_index("ix_tpc_trip_corrections_trip_id", table_name="tpc_trip_corrections")
    op.drop_table("tpc_trip_corrections")
