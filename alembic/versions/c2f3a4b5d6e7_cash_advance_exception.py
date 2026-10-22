"""cash advance: exception above the policy limit (last approver -> exception approver)

Revision ID: c2f3a4b5d6e7
Revises: b1e2f3a4c5d6
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op

revision = "c2f3a4b5d6e7"
down_revision = "b1e2f3a4c5d6"
branch_labels = None
depends_on = None

REQUEST_COLUMNS = [
    # pending / approved / rejected (NULL = no exception asked)
    ("exception_status", sa.String(20)),
    ("exception_amount", sa.Numeric(10, 2)),
    ("exception_pay_periods", sa.Integer()),
    ("exception_deduction_per_pay", sa.Numeric(10, 2)),
    ("exception_reason", sa.Text()),
    ("exception_requested_by_user_id", sa.Integer()),
    ("exception_requested_at", sa.DateTime()),
    ("exception_approver_user_id", sa.Integer()),
    ("exception_decided_at", sa.DateTime()),
    ("exception_remarks", sa.Text()),
]


def upgrade():
    for name, type_ in REQUEST_COLUMNS:
        op.add_column("tpc_cash_advance_requests", sa.Column(name, type_, nullable=True))
    # Who approves exceptions (Cash Advance Settings). NULL = a superadmin.
    op.add_column(
        "tpc_cash_advance_terms",
        sa.Column("exception_approver_user_id", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("tpc_cash_advance_terms", "exception_approver_user_id")
    for name, _ in reversed(REQUEST_COLUMNS):
        op.drop_column("tpc_cash_advance_requests", name)
