"""add payroll deductions table

Revision ID: ef5ccfbe8066
Revises: 8dea9cdde4b7
Create Date: 2026-08-14 15:49:45.429215

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef5ccfbe8066'
down_revision: Union[str, Sequence[str], None] = '8dea9cdde4b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payroll_deductions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cutoff_period", sa.String(length=50), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("department", sa.String(length=50), nullable=False),
        sa.Column(
            "gross_pay", sa.Numeric(precision=12, scale=2), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "sss_deduction", sa.Numeric(precision=12, scale=2), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "philhealth_deduction", sa.Numeric(precision=12, scale=2),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "pagibig_deduction", sa.Numeric(precision=12, scale=2),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "tardiness_deduction", sa.Numeric(precision=12, scale=2),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "undertime_deduction", sa.Numeric(precision=12, scale=2),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "absent_deduction", sa.Numeric(precision=12, scale=2),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "net_pay", sa.Numeric(precision=12, scale=2), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "employee_id", "cutoff_period",
            name="uq_payroll_deductions_emp_cutoff",
        ),
    )
 
    op.create_index(
        "ix_payroll_deductions_cutoff_period",
        "payroll_deductions",
        ["cutoff_period"],
    )
    op.create_index(
        "ix_payroll_deductions_employee_id",
        "payroll_deductions",
        ["employee_id"],
    )
 
 
def downgrade() -> None:
    op.drop_index(
        "ix_payroll_deductions_employee_id", table_name="payroll_deductions"
    )
    op.drop_index(
        "ix_payroll_deductions_cutoff_period", table_name="payroll_deductions"
    )
    op.drop_table("payroll_deductions")