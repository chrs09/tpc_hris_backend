"""Incentive Reports (made on a program's release date, approved per row)

Revision ID: i5d6e7f8a9b1
Revises: h4c5d6e7f8a0
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "i5d6e7f8a9b1"
down_revision = "h4c5d6e7f8a0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_incentive_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("tpc_incentive_programs.id"), nullable=False),
        sa.Column("program_name", sa.String(150), nullable=False),
        sa.Column("memo_no", sa.String(30), nullable=True),
        sa.Column("rule_type", sa.String(30), nullable=False),
        sa.Column("applies_to", sa.String(50), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("release_date", sa.Date(), nullable=False),
        sa.Column("settings_snapshot", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="FOR_REVIEW"),
        sa.Column("total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("return_note", sa.String(500), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("generated_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("released_by", sa.Integer(), nullable=True),
        sa.Column("release_method", sa.String(20), nullable=True),
        sa.Column("release_reference", sa.String(100), nullable=True),
        sa.Column("log", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tpc_incentive_reports_program_id", "tpc_incentive_reports", ["program_id"], unique=True)
    op.create_index("ix_tpc_incentive_reports_release_date", "tpc_incentive_reports", ["release_date"])
    op.create_index("ix_tpc_incentive_reports_status", "tpc_incentive_reports", ["status"])

    op.create_table(
        "tpc_incentive_report_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "report_id",
            sa.Integer(),
            sa.ForeignKey("tpc_incentive_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("employee_name", sa.String(150), nullable=False),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("group_name", sa.String(20), nullable=True),
        sa.Column("day", sa.Date(), nullable=True),
        sa.Column("computed_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_tpc_incentive_report_lines_report_id", "tpc_incentive_report_lines", ["report_id"])
    op.create_index("ix_tpc_incentive_report_lines_employee_id", "tpc_incentive_report_lines", ["employee_id"])


def downgrade():
    op.drop_table("tpc_incentive_report_lines")
    op.drop_table("tpc_incentive_reports")
