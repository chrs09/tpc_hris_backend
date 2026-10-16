"""employee internal work history (department / position / pay changes
with an effective date); payroll figures kept per department within a
cutoff (an employee moved mid-cutoff is paid in both)

Revision ID: b5e6f7a8c9d0
Revises: a4d5e6f7b8c9
Create Date: 2026-10-15
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "b5e6f7a8c9d0"
down_revision = "a4d5e6f7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_employee_job_changes",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "employee_id",
            sa.Integer(),
            sa.ForeignKey("tpc_employees.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("effective_date", sa.Date(), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False, server_default="CHANGE"),
        sa.Column("status", sa.String(20), nullable=False, server_default="APPLIED"),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("position", sa.String(100), nullable=True),
        sa.Column("employment_type", sa.String(20), nullable=True),
        sa.Column("payroll_type", sa.String(20), nullable=True),
        sa.Column("daily_rate", sa.Numeric(10, 2), nullable=True),
        sa.Column("monthly_basic", sa.Numeric(10, 2), nullable=True),
        sa.Column("monthly_allow", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "schedule_template_id",
            sa.Integer(),
            sa.ForeignKey("tpc_schedule_templates.id"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
    )

    # Starting row for everyone: today's values from the date hired.
    now = datetime.utcnow()
    op.execute(
        sa.text(
            """
            INSERT INTO tpc_employee_job_changes
              (employee_id, effective_date, kind, status, department, position,
               employment_type, payroll_type, daily_rate, monthly_basic,
               monthly_allow, schedule_template_id, reason, created_at, applied_at)
            SELECT id, COALESCE(date_hired, CURDATE()), 'HIRED', 'APPLIED',
                   department, position, employment_type, payroll_type, daily_rate,
                   monthly_basic, monthly_allow, schedule_template_id,
                   'Starting record (values when work history began)', :now, :now
            FROM tpc_employees
            """
        ).bindparams(now=now)
    )

    # One payroll row per employee per cutoff per part: a change inside
    # the cutoff splits it (segment = the part's first day; "" = whole).
    op.add_column(
        "payroll_deductions",
        sa.Column("segment", sa.String(20), nullable=False, server_default=""),
    )
    op.drop_constraint("uq_payroll_deductions_emp_cutoff", "payroll_deductions", type_="unique")
    op.create_unique_constraint(
        "uq_payroll_deductions_emp_cutoff_dept",
        "payroll_deductions",
        ["employee_id", "cutoff_period", "department", "segment"],
    )


def downgrade():
    op.drop_constraint("uq_payroll_deductions_emp_cutoff_dept", "payroll_deductions", type_="unique")
    op.create_unique_constraint(
        "uq_payroll_deductions_emp_cutoff",
        "payroll_deductions",
        ["employee_id", "cutoff_period"],
    )
    op.drop_column("payroll_deductions", "segment")
    op.drop_table("tpc_employee_job_changes")
