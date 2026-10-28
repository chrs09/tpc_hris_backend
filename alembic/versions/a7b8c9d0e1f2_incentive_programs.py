"""incentive programs table, seeded with memos 26-005 / 26-006

Incentive Policies page: one row per incentive program for a period
(trip tiers, daily cash, long distance, complete attendance) with its
amounts in `settings` JSON. Seeded with the August and September 2026
driver programs from memos 26-005 and 26-006.

Revision ID: a7b8c9d0e1f2
Revises: f5c6d7e8a9b0
Create Date: 2026-10-28
"""

import json
from datetime import date, datetime

import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f5c6d7e8a9b0"
branch_labels = None
depends_on = None

_MON_SAT = [0, 1, 2, 3, 4, 5]


def _tiers(tier3):
    return {
        "include_sundays": True,
        "tiers": [
            {"name": "Tier 1", "min_trips": 65, "amount": 8000},
            {"name": "Tier 2", "min_trips": 52, "amount": 5000},
            {"name": "Tier 3", "min_trips": 39, "amount": tier3},
        ],
    }


_SEED = [
    # Memo 26-005 -- August 2026.
    {
        "name": "Driver Incentive Program - Performance Tiers",
        "memo_no": "26-005",
        "rule_type": "trip_tiers",
        "period_start": date(2026, 8, 1),
        "period_end": date(2026, 8, 31),
        "release_date": date(2026, 9, 5),
        "settings": _tiers(2000),
    },
    {
        "name": "Driver Incentive Program - Daily Cash",
        "memo_no": "26-005",
        "rule_type": "daily_cash",
        "period_start": date(2026, 8, 1),
        "period_end": date(2026, 8, 31),
        "release_date": None,
        # No more 100 for the 1st trip; 200 for the 2nd, +100 for the
        # 3rd "and so on". Special trips excluded.
        "settings": {
            "days": _MON_SAT,
            "trip_amounts": [0, 200, 100],
            "repeat_last": True,
            "first_trip_before": None,
            "exclude_categories": [],
        },
    },
    # Memo 26-006 -- September 2026.
    {
        "name": "Driver Incentive Program - Performance Tiers",
        "memo_no": "26-006",
        "rule_type": "trip_tiers",
        "period_start": date(2026, 9, 1),
        "period_end": date(2026, 9, 30),
        "release_date": date(2026, 10, 5),
        "settings": _tiers(3000),
    },
    {
        "name": "Driver Incentive Program - Daily Cash (Early Birds)",
        "memo_no": "26-006",
        "rule_type": "daily_cash",
        "period_start": date(2026, 9, 1),
        "period_end": date(2026, 9, 30),
        "release_date": None,
        # 100 for a first trip before 6am, then 100 every following trip.
        "settings": {
            "days": _MON_SAT,
            "trip_amounts": [100, 100],
            "repeat_last": True,
            "first_trip_before": "06:00",
            "exclude_categories": [],
        },
    },
]


def upgrade():
    table = op.create_table(
        "tpc_incentive_programs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("memo_no", sa.String(30), nullable=True),
        sa.Column("rule_type", sa.String(30), nullable=False),
        sa.Column("applies_to", sa.String(50), nullable=False, server_default="drivers"),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("settings", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tpc_incentive_programs_id", "tpc_incentive_programs", ["id"])
    op.create_index("ix_tpc_incentive_programs_rule_type", "tpc_incentive_programs", ["rule_type"])
    op.create_index("ix_tpc_incentive_programs_period_start", "tpc_incentive_programs", ["period_start"])

    now = datetime.utcnow()
    op.bulk_insert(
        table,
        [
            {
                **row,
                "applies_to": "drivers",
                "settings": json.dumps(row["settings"]),
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for row in _SEED
        ],
    )


def downgrade():
    op.drop_index("ix_tpc_incentive_programs_period_start", table_name="tpc_incentive_programs")
    op.drop_index("ix_tpc_incentive_programs_rule_type", table_name="tpc_incentive_programs")
    op.drop_index("ix_tpc_incentive_programs_id", table_name="tpc_incentive_programs")
    op.drop_table("tpc_incentive_programs")
