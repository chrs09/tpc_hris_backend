"""Finance -> Loan Amortization (SSS / Pag-IBIG loans paid by payroll)

- tpc_employee_loans: amount borrowed, monthly amortization, terms, start
  month, schedule (split / 15th / month end), already paid.
- tpc_employee_loan_payments: one per loan per cutoff deducted (or a
  payment recorded by hand).
- payroll_deductions.pagibig_loan (Deductions step, like sss_loan).

Revision ID: a7b8c9d0e1f3
Revises: f6a7b8c9d0e2
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f3"
down_revision = "f6a7b8c9d0e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_employee_loans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("employee_id", sa.Integer(), nullable=False, index=True),
        sa.Column("loan_type", sa.String(20), nullable=False),
        sa.Column("reference_no", sa.String(60), nullable=True),
        sa.Column("loan_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("monthly_amortization", sa.Numeric(12, 2), nullable=False),
        sa.Column("terms_months", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("deduct_schedule", sa.String(10), nullable=False, server_default="SPLIT"),
        sa.Column("opening_paid", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(12), nullable=False, server_default="ACTIVE"),
        sa.Column("notes", sa.String(300), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "tpc_employee_loan_payments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "loan_id", sa.Integer(),
            sa.ForeignKey("tpc_employee_loans.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("cutoff_period", sa.String(50), nullable=True, index=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("recorded_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.add_column("payroll_deductions", sa.Column("pagibig_loan", sa.Numeric(12, 2), nullable=True))


def downgrade():
    op.drop_column("payroll_deductions", "pagibig_loan")
    op.drop_table("tpc_employee_loan_payments")
    op.drop_table("tpc_employee_loans")
