"""government contribution ticks per employee + pay run contributions step

- tpc_employee_government_details: has_sss / has_philhealth / has_pagibig /
  has_tax. Monthly-paid employees start ticked (payroll only deducted for
  them before), and every employee gets a row.
- payroll_deductions: withholding_tax (kept like SSS etc. so an edit at the
  Contributions step survives a regenerate).
- tpc_payroll_runs: reviewed_at/by (For Review -> Contributions) and
  contributions_at/by (Contributions -> Head Review).

Revision ID: e5f6a7b8c9d1
Revises: d4e5f6a7b8c0
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d1"
down_revision = "d4e5f6a7b8c0"
branch_labels = None
depends_on = None

FLAGS = ("has_sss", "has_philhealth", "has_pagibig", "has_tax")


def upgrade():
    for flag in FLAGS:
        op.add_column(
            "tpc_employee_government_details",
            sa.Column(flag, sa.Boolean(), nullable=False, server_default="0"),
        )
    # Every employee gets a row (most screens create it lazily).
    op.execute(
        """
        INSERT INTO tpc_employee_government_details (employee_id)
        SELECT e.id FROM tpc_employees e
        WHERE NOT EXISTS (
            SELECT 1 FROM tpc_employee_government_details g WHERE g.employee_id = e.id
        )
        """
    )
    op.execute(
        """
        UPDATE tpc_employee_government_details
        SET has_sss = 1, has_philhealth = 1, has_pagibig = 1, has_tax = 1
        WHERE employee_id IN (
            SELECT id FROM tpc_employees WHERE payroll_type = 'Monthly'
        )
        """
    )

    op.add_column(
        "payroll_deductions",
        sa.Column("withholding_tax", sa.Numeric(12, 2), nullable=True),
    )

    op.add_column("tpc_payroll_runs", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column("tpc_payroll_runs", sa.Column("reviewed_by", sa.Integer(), nullable=True))
    op.add_column("tpc_payroll_runs", sa.Column("contributions_at", sa.DateTime(), nullable=True))
    op.add_column("tpc_payroll_runs", sa.Column("contributions_by", sa.Integer(), nullable=True))


def downgrade():
    for col in ("contributions_by", "contributions_at", "reviewed_by", "reviewed_at"):
        op.drop_column("tpc_payroll_runs", col)
    op.drop_column("payroll_deductions", "withholding_tax")
    for flag in FLAGS:
        op.drop_column("tpc_employee_government_details", flag)
