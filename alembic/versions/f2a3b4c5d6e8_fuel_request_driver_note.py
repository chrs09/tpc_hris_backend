"""Fuel request: note from the person filing it (shown to the coordinator)

Revision ID: f2a3b4c5d6e8
Revises: e1f2a3b4c5d7
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "f2a3b4c5d6e8"
down_revision = "e1f2a3b4c5d7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_fuel_requests", sa.Column("driver_note", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("tpc_fuel_requests", "driver_note")
