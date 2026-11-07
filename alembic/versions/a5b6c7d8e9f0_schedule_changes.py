"""schedule changes: a different time in / out for one date, with approval

- tpc_employees.allow_schedule_change: who may request one (per employee)
- tpc_schedule_changes: the requests

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "a5b6c7d8e9f0"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_employees",
        sa.Column("allow_schedule_change", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "tpc_schedule_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("tpc_employees.id"), nullable=False),
        sa.Column("schedule_date", sa.Date(), nullable=False),
        sa.Column("time_in", sa.Time(), nullable=False),
        sa.Column("time_out", sa.Time(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("approval_chain", sa.Text(), nullable=True),
        sa.Column("approval_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approval_log", sa.Text(), nullable=True),
        sa.Column("filed_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tpc_schedule_changes_id", "tpc_schedule_changes", ["id"])
    op.create_index("ix_tpc_schedule_changes_employee_id", "tpc_schedule_changes", ["employee_id"])
    op.create_index("ix_tpc_schedule_changes_schedule_date", "tpc_schedule_changes", ["schedule_date"])
    op.create_index("ix_tpc_schedule_changes_status", "tpc_schedule_changes", ["status"])


def downgrade():
    op.drop_table("tpc_schedule_changes")
    op.drop_column("tpc_employees", "allow_schedule_change")
