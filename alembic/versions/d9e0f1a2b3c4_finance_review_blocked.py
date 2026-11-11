"""finance review: "blocked" (Finance marks a trip's documents not valid)

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op

revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None

FK_NAME = "fk_finance_review_blocked_by"


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tpc_trip_finance_reviews
        MODIFY COLUMN status ENUM(
            'office_review',
            'finance_review',
            'approved',
            'returned',
            'blocked'
        ) NOT NULL
    """)
    op.add_column(
        "tpc_trip_finance_reviews",
        sa.Column("blocked_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        FK_NAME, "tpc_trip_finance_reviews", "tpc_users", ["blocked_by_user_id"], ["id"]
    )
    op.add_column(
        "tpc_trip_finance_reviews",
        sa.Column("block_reason", sa.String(1000), nullable=True),
    )
    op.add_column(
        "tpc_trip_finance_reviews",
        sa.Column("blocked_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.execute(
        "UPDATE tpc_trip_finance_reviews SET status = 'finance_review' WHERE status = 'blocked'"
    )
    op.drop_column("tpc_trip_finance_reviews", "blocked_at")
    op.drop_column("tpc_trip_finance_reviews", "block_reason")
    op.drop_constraint(FK_NAME, "tpc_trip_finance_reviews", type_="foreignkey")
    op.drop_column("tpc_trip_finance_reviews", "blocked_by_user_id")
    op.execute("""
        ALTER TABLE tpc_trip_finance_reviews
        MODIFY COLUMN status ENUM(
            'office_review',
            'finance_review',
            'approved',
            'returned'
        ) NOT NULL
    """)
