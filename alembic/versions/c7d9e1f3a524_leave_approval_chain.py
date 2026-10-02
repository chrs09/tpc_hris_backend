"""leave approval chain

Leave goes through the Org Chart heads (Leave ticked), step by step, like
cash advance and overtime.

Revision ID: c7d9e1f3a524
Revises: a9c3e5f7b812
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "c7d9e1f3a524"
down_revision = "a9c3e5f7b812"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_leave_requests", sa.Column("approval_chain", sa.Text(), nullable=True))
    op.add_column(
        "tpc_leave_requests",
        sa.Column("approval_step", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("tpc_leave_requests", sa.Column("approval_log", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("tpc_leave_requests", "approval_log")
    op.drop_column("tpc_leave_requests", "approval_step")
    op.drop_column("tpc_leave_requests", "approval_chain")
