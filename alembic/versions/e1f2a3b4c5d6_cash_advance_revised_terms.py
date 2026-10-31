"""cash advance: employee re-acknowledges revised terms after an exception

An approved exception can change the amount and repayment the employee
agreed to when filing (e.g. 1k per payroll -> 2k per payroll). They now
accept or decline the new terms before the money can be released or
deducted. Requests approved before this stay as they are (no acknowledgement
needed).

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-10-31
"""

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None

_TABLE = "tpc_cash_advance_requests"


def upgrade():
    op.add_column(_TABLE, sa.Column("revised_terms_status", sa.String(20), nullable=True))
    op.add_column(_TABLE, sa.Column("revised_terms_previous_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column(_TABLE, sa.Column("revised_terms_previous_per_pay", sa.Numeric(10, 2), nullable=True))
    op.add_column(_TABLE, sa.Column("revised_terms_required_at", sa.DateTime(), nullable=True))
    op.add_column(_TABLE, sa.Column("revised_terms_responded_at", sa.DateTime(), nullable=True))
    op.add_column(_TABLE, sa.Column("revised_terms_remarks", sa.Text(), nullable=True))


def downgrade():
    op.drop_column(_TABLE, "revised_terms_remarks")
    op.drop_column(_TABLE, "revised_terms_responded_at")
    op.drop_column(_TABLE, "revised_terms_required_at")
    op.drop_column(_TABLE, "revised_terms_previous_per_pay")
    op.drop_column(_TABLE, "revised_terms_previous_amount")
    op.drop_column(_TABLE, "revised_terms_status")
