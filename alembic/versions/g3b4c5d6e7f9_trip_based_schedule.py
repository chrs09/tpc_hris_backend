"""Work schedules: trip-based type (work days only, rest days get a premium)

Revision ID: g3b4c5d6e7f9
Revises: f2a3b4c5d6e8
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "g3b4c5d6e7f9"
down_revision = "f2a3b4c5d6e8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_schedule_templates",
        sa.Column("is_trip_based", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("tpc_schedule_templates", sa.Column("work_days", sa.String(40), nullable=True))


def downgrade():
    op.drop_column("tpc_schedule_templates", "work_days")
    op.drop_column("tpc_schedule_templates", "is_trip_based")
