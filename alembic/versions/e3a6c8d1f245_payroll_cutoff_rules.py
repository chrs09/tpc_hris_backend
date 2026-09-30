"""payroll cutoff rules

Payroll cutoffs per department, set on the Payroll Cutoffs page instead
of hard-coded in the frontend. Seeded with the schedules that were
hard-coded, plus WingvanDriver on the same schedule as the other drivers.

Revision ID: e3a6c8d1f245
Revises: d7f2b9c4e118
Create Date: 2026-09-30
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "e3a6c8d1f245"
down_revision = "d7f2b9c4e118"
branch_labels = None
depends_on = None

# (department, type, first_start, second_start, first_payout, second_payout,
#  week_start, payout_offset)
DRIVER_SCHEDULE = ("semi_monthly", 1, 16, 0, 15, None, None)
SEED = [
    ("Admin", "semi_monthly", 11, 26, 0, 15, None, None),
    ("Motorpool", "weekly", None, None, None, None, 4, 3),
    *[
        (dept, *DRIVER_SCHEDULE)
        for dept in (
            "CdcDriver",
            "CdcHelper",
            "CpdcDriver",
            "CpdcHelper",
            "Dumptruck",
            "Labor",
            "WingvanDriver",
        )
    ],
]


def upgrade():
    table = op.create_table(
        "tpc_payroll_cutoff_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("department", sa.String(50), nullable=False),
        sa.Column("schedule_type", sa.String(20), nullable=False),
        sa.Column("first_start_day", sa.Integer(), nullable=True),
        sa.Column("second_start_day", sa.Integer(), nullable=True),
        sa.Column("first_payout_day", sa.Integer(), nullable=True),
        sa.Column("second_payout_day", sa.Integer(), nullable=True),
        sa.Column("week_start_day", sa.Integer(), nullable=True),
        sa.Column("payout_offset_days", sa.Integer(), nullable=True),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("tpc_users.id"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_tpc_payroll_cutoff_rules_department",
        "tpc_payroll_cutoff_rules",
        ["department"],
        unique=True,
    )
    now = datetime.utcnow()
    op.bulk_insert(
        table,
        [
            {
                "department": dept,
                "schedule_type": kind,
                "first_start_day": s1,
                "second_start_day": s2,
                "first_payout_day": p1,
                "second_payout_day": p2,
                "week_start_day": ws,
                "payout_offset_days": off,
                "updated_at": now,
            }
            for dept, kind, s1, s2, p1, p2, ws, off in SEED
        ],
    )


def downgrade():
    op.drop_index(
        "ix_tpc_payroll_cutoff_rules_department", table_name="tpc_payroll_cutoff_rules"
    )
    op.drop_table("tpc_payroll_cutoff_rules")
