"""fuel request: org chart approval chain (heads approve before the fuel code)

Revision ID: a0d1e2f3b4c5
Revises: f9c0d1e2a3b4
Create Date: 2026-10-20
"""

import sqlalchemy as sa
from alembic import op

revision = "a0d1e2f3b4c5"
down_revision = "f9c0d1e2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_fuel_requests", sa.Column("approval_chain", sa.Text(), nullable=True))
    op.add_column(
        "tpc_fuel_requests",
        sa.Column("approval_step", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("tpc_fuel_requests", sa.Column("approval_log", sa.Text(), nullable=True))
    op.add_column(
        "tpc_fuel_requests",
        sa.Column("awaiting_approval", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("tpc_fuel_requests", "awaiting_approval")
    op.drop_column("tpc_fuel_requests", "approval_log")
    op.drop_column("tpc_fuel_requests", "approval_step")
    op.drop_column("tpc_fuel_requests", "approval_chain")
