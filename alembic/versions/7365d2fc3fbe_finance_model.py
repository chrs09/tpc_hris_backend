"""finance model

Revision ID: 7365d2fc3fbe
Revises: 1542ba576674
Create Date: 2026-07-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7365d2fc3fbe"
down_revision = "1542ba576674"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------
    # 1. Add 'PENDING_FINANCE_REVIEW' to the status enum on tpc_trips.
    #
    # MySQL has no ALTER TYPE — enums are inline column definitions,
    # so the only way to add a value is to redefine the whole column
    # with the new value list included. This is a metadata-only
    # operation in MySQL (fast, no table rewrite), but it does need
    # the full set of existing values restated exactly.
    # ------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE tpc_trips
        MODIFY COLUMN status ENUM(
            'ASSIGNED',
            'ACTIVE',
            'PENDING_APPROVAL',
            'PENDING_FINANCE_REVIEW',
            'COMPLETED',
            'CANCELLED'
        ) NOT NULL
        """
    )

    # ------------------------------------------------------------
    # 2. Create tpc_trip_finance_reviews.
    #    MySQL enums are declared inline on the column — no separate
    #    CREATE TYPE step like Postgres needed.
    # ------------------------------------------------------------
    op.create_table(
        "tpc_trip_finance_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "trip_id",
            sa.Integer(),
            sa.ForeignKey("tpc_trips.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column(
            "coordinator_id",
            sa.Integer(),
            sa.ForeignKey("tpc_users.id"),
            nullable=False,
        ),
        sa.Column("coordinator_remarks", sa.String(length=1000), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("for_review", "approved", name="finance_review_status_enum"),
            nullable=False,
            server_default="for_review",
        ),
        sa.Column(
            "finance_reviewer_id",
            sa.Integer(),
            sa.ForeignKey("tpc_users.id"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    # ------------------------------------------------------------
    # 1. Drop the finance review table first (it FKs to tpc_trips).
    # ------------------------------------------------------------
    op.drop_table("tpc_trip_finance_reviews")

    # ------------------------------------------------------------
    # 2. Remove 'PENDING_FINANCE_REVIEW' from the status enum.
    #
    # If any trip row is currently PENDING_FINANCE_REVIEW, MySQL
    # (in default strict mode) will raise an error on this MODIFY
    # rather than silently truncating the value — which is what you
    # want. Move those trips to another status first if you ever
    # need to downgrade against real data.
    # ------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE tpc_trips
        MODIFY COLUMN status ENUM(
            'ASSIGNED',
            'ACTIVE',
            'PENDING_APPROVAL',
            'COMPLETED',
            'CANCELLED'
        ) NOT NULL
        """
    )