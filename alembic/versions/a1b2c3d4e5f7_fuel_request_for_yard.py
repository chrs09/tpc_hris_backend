"""fuel request for_yard: filed by a yard head for a unit with no driver

Revision ID: a1b2c3d4e5f7
Revises: f0a1b2c3d4e5
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_fuel_requests",
        sa.Column("for_yard", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("tpc_fuel_requests", "for_yard")
