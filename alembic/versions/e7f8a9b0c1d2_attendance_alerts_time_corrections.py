"""attendance: missed time in alerts for heads, and time correction requests

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_attendance_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("tpc_employees.id"), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("scheduled_in", sa.Time(), nullable=True),
        sa.Column("head_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("decision", sa.String(20), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("head_emailed_at", sa.DateTime(), nullable=True),
        sa.Column("employee_emailed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("employee_id", "attendance_date", name="uq_attendance_alert_day"),
    )
    op.create_index("ix_tpc_attendance_alerts_employee_id", "tpc_attendance_alerts", ["employee_id"])
    op.create_index("ix_tpc_attendance_alerts_attendance_date", "tpc_attendance_alerts", ["attendance_date"])
    op.create_index("ix_tpc_attendance_alerts_head_user_id", "tpc_attendance_alerts", ["head_user_id"])
    op.create_index("ix_tpc_attendance_alerts_status", "tpc_attendance_alerts", ["status"])

    op.create_table(
        "tpc_time_corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("tpc_employees.id"), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("time_in", sa.DateTime(), nullable=True),
        sa.Column("time_out", sa.DateTime(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("approval_chain", sa.Text(), nullable=True),
        sa.Column("approval_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approval_log", sa.Text(), nullable=True),
        sa.Column("filed_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tpc_time_corrections_employee_id", "tpc_time_corrections", ["employee_id"])
    op.create_index("ix_tpc_time_corrections_attendance_date", "tpc_time_corrections", ["attendance_date"])
    op.create_index("ix_tpc_time_corrections_status", "tpc_time_corrections", ["status"])


def downgrade():
    op.drop_table("tpc_time_corrections")
    op.drop_table("tpc_attendance_alerts")
