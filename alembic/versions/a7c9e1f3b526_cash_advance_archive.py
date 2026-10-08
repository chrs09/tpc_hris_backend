"""cash advance: archive (hide from All Requests)

Revision ID: a7c9e1f3b526
Revises: f6b8d0e2a415
Create Date: 2026-10-08
"""

import sqlalchemy as sa
from alembic import op

revision = "a7c9e1f3b526"
down_revision = "f6b8d0e2a415"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_cash_advance_requests",
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("tpc_cash_advance_requests", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("tpc_cash_advance_requests", sa.Column("archived_by_user_id", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("tpc_cash_advance_requests", "archived_by_user_id")
    op.drop_column("tpc_cash_advance_requests", "archived_at")
    op.drop_column("tpc_cash_advance_requests", "is_archived")
