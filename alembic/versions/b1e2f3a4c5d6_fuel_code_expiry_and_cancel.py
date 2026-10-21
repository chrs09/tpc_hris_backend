"""fuel request: code expiry (set when issuing) and driver's cancel-code reason

Revision ID: b1e2f3a4c5d6
Revises: a0d1e2f3b4c5
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from alembic import op

revision = "b1e2f3a4c5d6"
down_revision = "a0d1e2f3b4c5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_fuel_requests", sa.Column("code_expires_at", sa.DateTime(), nullable=True))
    op.add_column("tpc_fuel_requests", sa.Column("code_cancelled_at", sa.DateTime(), nullable=True))
    op.add_column("tpc_fuel_requests", sa.Column("cancel_reason", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("tpc_fuel_requests", "cancel_reason")
    op.drop_column("tpc_fuel_requests", "code_cancelled_at")
    op.drop_column("tpc_fuel_requests", "code_expires_at")
