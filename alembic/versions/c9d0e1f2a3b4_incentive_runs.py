"""incentive runs + their lines (incentives paid out apart from payroll)

An incentive run computes Incentive Policies programs for a period with
the programs' settings frozen, then Draft -> Approved -> Released; its
lines are the history of what each person earned.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_incentive_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("program_ids", sa.Text(), nullable=False),
        sa.Column("programs_snapshot", sa.Text(), nullable=True),
        sa.Column("release_method", sa.String(20), nullable=False, server_default="cash"),
        sa.Column("payroll_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("return_note", sa.String(500), nullable=True),
        sa.Column("total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("employee_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("release_reference", sa.String(100), nullable=True),
        sa.Column("released_on", sa.Date(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("generated_by", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("released_by", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_by", sa.Integer(), nullable=True),
        sa.Column("log", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tpc_incentive_runs_id", "tpc_incentive_runs", ["id"])
    op.create_index("ix_tpc_incentive_runs_period_start", "tpc_incentive_runs", ["period_start"])
    op.create_index("ix_tpc_incentive_runs_status", "tpc_incentive_runs", ["status"])

    op.create_table(
        "tpc_incentive_run_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("tpc_incentive_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("employee_name", sa.String(150), nullable=False),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("group_name", sa.String(20), nullable=True),
        sa.Column("program_id", sa.Integer(), nullable=True),
        sa.Column("program_name", sa.String(150), nullable=False),
        sa.Column("rule_type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("is_adjustment", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tpc_incentive_run_lines_id", "tpc_incentive_run_lines", ["id"])
    op.create_index("ix_tpc_incentive_run_lines_run_id", "tpc_incentive_run_lines", ["run_id"])
    op.create_index("ix_tpc_incentive_run_lines_employee_id", "tpc_incentive_run_lines", ["employee_id"])
    op.create_index("ix_tpc_incentive_run_lines_program_id", "tpc_incentive_run_lines", ["program_id"])


def downgrade():
    op.drop_table("tpc_incentive_run_lines")
    op.drop_index("ix_tpc_incentive_runs_status", table_name="tpc_incentive_runs")
    op.drop_index("ix_tpc_incentive_runs_period_start", table_name="tpc_incentive_runs")
    op.drop_index("ix_tpc_incentive_runs_id", table_name="tpc_incentive_runs")
    op.drop_table("tpc_incentive_runs")
