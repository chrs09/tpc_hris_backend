"""fuel request: odometer reading typed by the driver (with the photo)

Revision ID: e8b9c0d1f2a3
Revises: d7a8b9c0e1f2
Create Date: 2026-10-19
"""

import sqlalchemy as sa
from alembic import op

revision = "e8b9c0d1f2a3"
down_revision = "d7a8b9c0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_fuel_requests", sa.Column("odometer_reading", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("tpc_fuel_requests", "odometer_reading")
