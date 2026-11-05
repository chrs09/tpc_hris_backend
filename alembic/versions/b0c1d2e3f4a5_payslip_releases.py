"""payslip releases: payslips released to employees after payroll is locked

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision = "b0c1d2e3f4a5"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_payslip_releases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("department", sa.String(50), nullable=False),
        sa.Column("cutoff_period", sa.String(50), nullable=False),
        sa.Column("segment", sa.String(20), nullable=False, server_default=""),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("payout_date", sa.String(20), nullable=True),
        sa.Column("gross_pay", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("net_pay", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("snapshot", sa.Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("released_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint(
            "employee_id",
            "department",
            "cutoff_period",
            "segment",
            name="uq_payslip_release_emp_payroll",
        ),
    )
    op.create_index("ix_tpc_payslip_releases_employee_id", "tpc_payslip_releases", ["employee_id"])
    op.create_index("ix_tpc_payslip_releases_cutoff_period", "tpc_payslip_releases", ["cutoff_period"])


def downgrade():
    op.drop_index("ix_tpc_payslip_releases_cutoff_period", table_name="tpc_payslip_releases")
    op.drop_index("ix_tpc_payslip_releases_employee_id", table_name="tpc_payslip_releases")
    op.drop_table("tpc_payslip_releases")
