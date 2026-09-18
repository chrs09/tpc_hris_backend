"""add RETURNED status + return columns to trip_finance_reviews

Revision ID: a7c2e5f8b1d3
Revises: f3a1c7d9e2b4
Create Date: 2026-09-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7c2e5f8b1d3"
down_revision = "f3a1c7d9e2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tpc_trip_finance_reviews
        MODIFY COLUMN status ENUM(
            'office_review',
            'finance_review',
            'approved',
            'returned'
        ) NOT NULL
    """)

    op.add_column(
        "tpc_trip_finance_reviews",
        sa.Column(
            "returned_by_user_id",
            sa.Integer(),
            sa.ForeignKey("tpc_users.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "tpc_trip_finance_reviews",
        sa.Column("return_reason", sa.String(1000), nullable=True),
    )
    op.add_column(
        "tpc_trip_finance_reviews",
        sa.Column("returned_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tpc_trip_finance_reviews", "returned_at")
    op.drop_column("tpc_trip_finance_reviews", "return_reason")
    op.drop_column("tpc_trip_finance_reviews", "returned_by_user_id")

    op.execute("""
        ALTER TABLE tpc_trip_finance_reviews
        MODIFY COLUMN status ENUM(
            'office_review',
            'finance_review',
            'approved'
        ) NOT NULL
    """)
