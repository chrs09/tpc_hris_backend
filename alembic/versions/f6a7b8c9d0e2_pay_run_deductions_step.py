"""pay run Deductions step

- payroll_deductions: sss_loan, other_deduction, other_deduction_note
  (were only kept on the page; now saved so a regenerate keeps them).
- tpc_payroll_runs: deductions_confirmed_at / _by (Submit for Review needs
  the deductions confirmed; Generate again clears it).

Revision ID: f6a7b8c9d0e2
Revises: e5f6a7b8c9d1
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e2"
down_revision = "e5f6a7b8c9d1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payroll_deductions", sa.Column("sss_loan", sa.Numeric(12, 2), nullable=True))
    op.add_column("payroll_deductions", sa.Column("other_deduction", sa.Numeric(12, 2), nullable=True))
    op.add_column("payroll_deductions", sa.Column("other_deduction_note", sa.String(200), nullable=True))
    op.add_column("tpc_payroll_runs", sa.Column("deductions_confirmed_at", sa.DateTime(), nullable=True))
    op.add_column("tpc_payroll_runs", sa.Column("deductions_confirmed_by", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("tpc_payroll_runs", "deductions_confirmed_by")
    op.drop_column("tpc_payroll_runs", "deductions_confirmed_at")
    op.drop_column("payroll_deductions", "other_deduction_note")
    op.drop_column("payroll_deductions", "other_deduction")
    op.drop_column("payroll_deductions", "sss_loan")
