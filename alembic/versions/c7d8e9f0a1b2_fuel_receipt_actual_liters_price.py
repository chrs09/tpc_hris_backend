"""fuel request: actual liters and price typed from the receipt

Revision ID: c7d8e9f0a1b2
Revises: b3c4d5e6f7a8
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from alembic import op

revision = "c7d8e9f0a1b2"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_fuel_requests", sa.Column("actual_liters", sa.Numeric(10, 2), nullable=True))
    op.add_column("tpc_fuel_requests", sa.Column("actual_price", sa.Numeric(12, 2), nullable=True))


def downgrade():
    op.drop_column("tpc_fuel_requests", "actual_price")
    op.drop_column("tpc_fuel_requests", "actual_liters")
