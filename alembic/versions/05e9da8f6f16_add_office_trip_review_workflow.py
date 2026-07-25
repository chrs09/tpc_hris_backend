"""add office trip review workflow

Revision ID: 05e9da8f6f16
Revises: f2847626a52a
Create Date: 2026-07-20 13:52:55.096297
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "05e9da8f6f16"
down_revision: Union[str, Sequence[str], None] = "f2847626a52a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================
    # 1. ADD PENDING_OFFICE_REVIEW TO TRIP STATUS ENUM
    # =========================================================
    #
    # OLD:
    # ASSIGNED
    # ACTIVE
    # PENDING_APPROVAL
    # PENDING_FINANCE_REVIEW
    # COMPLETED
    # CANCELLED
    #
    # NEW:
    # ASSIGNED
    # ACTIVE
    # PENDING_APPROVAL
    # PENDING_OFFICE_REVIEW
    # PENDING_FINANCE_REVIEW
    # COMPLETED
    # CANCELLED
    #
    # Existing trip statuses remain valid.
    # =========================================================

    op.execute(
        """
        ALTER TABLE tpc_trips
        MODIFY COLUMN status
        ENUM(
            'ASSIGNED',
            'ACTIVE',
            'PENDING_APPROVAL',
            'PENDING_OFFICE_REVIEW',
            'PENDING_FINANCE_REVIEW',
            'COMPLETED',
            'CANCELLED'
        )
        NOT NULL
        """
    )

    # =========================================================
    # 2. ADD COORDINATOR SETTLEMENT DATE
    # =========================================================
    #
    # Start as nullable because existing rows do not yet have
    # this value. We will backfill them before making it
    # NOT NULL.
    # =========================================================

    op.add_column(
        "tpc_trip_finance_reviews",
        sa.Column(
            "coordinator_settlement_date",
            sa.DateTime(),
            nullable=True,
        ),
    )

    # =========================================================
    # 3. ADD OFFICE REVIEW COLUMNS
    # =========================================================

    op.add_column(
        "tpc_trip_finance_reviews",
        sa.Column(
            "office_reviewer_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "tpc_trip_finance_reviews",
        sa.Column(
            "office_remarks",
            sa.String(length=1000),
            nullable=True,
        ),
    )

    op.add_column(
        "tpc_trip_finance_reviews",
        sa.Column(
            "office_reviewed_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    # =========================================================
    # 4. ADD FOREIGN KEY FOR OFFICE REVIEWER
    # =========================================================

    op.create_foreign_key(
        "fk_trip_finance_reviews_office_reviewer",
        "tpc_trip_finance_reviews",
        "tpc_users",
        ["office_reviewer_id"],
        ["id"],
    )

    # =========================================================
    # 5. BACKFILL COORDINATOR SETTLEMENT DATE
    # =========================================================
    #
    # Existing review records were created when the coordinator
    # approved the trip under the old workflow.
    #
    # Therefore submitted_at is the best historical equivalent
    # of coordinator_settlement_date.
    # =========================================================

    op.execute(
        """
        UPDATE tpc_trip_finance_reviews
        SET coordinator_settlement_date = submitted_at
        WHERE coordinator_settlement_date IS NULL
        """
    )

    # =========================================================
    # 6. MAKE COORDINATOR SETTLEMENT DATE NOT NULL
    # =========================================================

    op.alter_column(
        "tpc_trip_finance_reviews",
        "coordinator_settlement_date",
        existing_type=sa.DateTime(),
        nullable=False,
    )

    # =========================================================
    # 7. TEMPORARILY EXPAND FINANCE REVIEW STATUS ENUM
    # =========================================================
    #
    # OLD:
    # for_review
    # approved
    #
    # TEMPORARY:
    # for_review
    # office_review
    # finance_review
    # approved
    #
    # We MUST keep "for_review" temporarily because existing
    # records may still contain it.
    # =========================================================

    op.execute(
        """
        ALTER TABLE tpc_trip_finance_reviews
        MODIFY COLUMN status
        ENUM(
            'for_review',
            'office_review',
            'finance_review',
            'approved'
        )
        NOT NULL
        """
    )

    # =========================================================
    # 8. MIGRATE EXISTING FOR_REVIEW RECORDS
    # =========================================================
    #
    # Before this migration, coordinator-approved trips went
    # directly to Finance.
    #
    # Therefore existing "for_review" records should become
    # "finance_review", NOT "office_review".
    #
    # This preserves the old workflow for trips already waiting
    # for Finance.
    # =========================================================

    op.execute(
        """
        UPDATE tpc_trip_finance_reviews
        SET status = 'finance_review'
        WHERE status = 'for_review'
        """
    )

    # =========================================================
    # 9. REMOVE OLD FOR_REVIEW ENUM VALUE
    # =========================================================
    #
    # FINAL:
    # office_review
    # finance_review
    # approved
    # =========================================================

    op.execute(
        """
        ALTER TABLE tpc_trip_finance_reviews
        MODIFY COLUMN status
        ENUM(
            'office_review',
            'finance_review',
            'approved'
        )
        NOT NULL
        """
    )


def downgrade() -> None:
    # =========================================================
    # 1. TEMPORARILY ADD OLD FOR_REVIEW STATUS BACK
    # =========================================================
    #
    # We cannot immediately remove office_review and
    # finance_review because rows may currently use them.
    # =========================================================

    op.execute(
        """
        ALTER TABLE tpc_trip_finance_reviews
        MODIFY COLUMN status
        ENUM(
            'for_review',
            'office_review',
            'finance_review',
            'approved'
        )
        NOT NULL
        """
    )

    # =========================================================
    # 2. CONVERT NEW PENDING REVIEW STATUSES TO OLD FOR_REVIEW
    # =========================================================
    #
    # Under the old application model there was only:
    #
    # for_review
    # approved
    #
    # Both Office and Finance pending reviews therefore become
    # for_review when downgrading.
    # =========================================================

    op.execute(
        """
        UPDATE tpc_trip_finance_reviews
        SET status = 'for_review'
        WHERE status IN (
            'office_review',
            'finance_review'
        )
        """
    )

    # =========================================================
    # 3. RESTORE ORIGINAL FINANCE REVIEW ENUM
    # =========================================================

    op.execute(
        """
        ALTER TABLE tpc_trip_finance_reviews
        MODIFY COLUMN status
        ENUM(
            'for_review',
            'approved'
        )
        NOT NULL
        """
    )

    # =========================================================
    # 4. MOVE PENDING OFFICE TRIPS BACK TO PENDING FINANCE
    # =========================================================
    #
    # The old TripStatus enum does not contain
    # PENDING_OFFICE_REVIEW.
    #
    # We MUST convert those rows before removing that ENUM value.
    # =========================================================

    op.execute(
        """
        UPDATE tpc_trips
        SET status = 'PENDING_FINANCE_REVIEW'
        WHERE status = 'PENDING_OFFICE_REVIEW'
        """
    )

    # =========================================================
    # 5. RESTORE ORIGINAL TRIP STATUS ENUM
    # =========================================================

    op.execute(
        """
        ALTER TABLE tpc_trips
        MODIFY COLUMN status
        ENUM(
            'ASSIGNED',
            'ACTIVE',
            'PENDING_APPROVAL',
            'PENDING_FINANCE_REVIEW',
            'COMPLETED',
            'CANCELLED'
        )
        NOT NULL
        """
    )

    # =========================================================
    # 6. DROP OFFICE REVIEWER FOREIGN KEY
    # =========================================================

    op.drop_constraint(
        "fk_trip_finance_reviews_office_reviewer",
        "tpc_trip_finance_reviews",
        type_="foreignkey",
    )

    # =========================================================
    # 7. DROP NEW COLUMNS
    # =========================================================

    op.drop_column(
        "tpc_trip_finance_reviews",
        "office_reviewed_at",
    )

    op.drop_column(
        "tpc_trip_finance_reviews",
        "office_remarks",
    )

    op.drop_column(
        "tpc_trip_finance_reviews",
        "office_reviewer_id",
    )

    op.drop_column(
        "tpc_trip_finance_reviews",
        "coordinator_settlement_date",
    )