"""Finance -> CA Corrections: adjustment / reversal requests

Revision ID: c9d0e1f2a3b5
Revises: b8c9d0e1f2a4
Create Date: 2026-11-23
"""

import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b5"
down_revision = "b8c9d0e1f2a4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_cash_advance_corrections",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "cash_advance_request_id", sa.Integer(),
            sa.ForeignKey("tpc_cash_advance_requests.id"), nullable=False, index=True,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("change", sa.Numeric(12, 2), nullable=True),
        sa.Column("deduction_log_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("cutoff_period", sa.String(50), nullable=True),
        sa.Column("balance_before", sa.Numeric(12, 2), nullable=True),
        sa.Column("owed_before", sa.Numeric(12, 2), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("applied_log_id", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_table("tpc_cash_advance_corrections")
