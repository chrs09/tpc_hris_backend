"""add pending manual approval trip status

Revision ID: eba8f5c29516
Revises: e8c7342b6cac
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'eba8f5c29516'
down_revision: Union[str, Sequence[str], None] = 'e8c7342b6cac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """PENDING_MANUAL_APPROVAL: a trip entered by a coordinator_admin in
    Trip Manual Entries, waiting for a superadmin before it goes to Trip
    Approvals."""
    op.execute("""
        ALTER TABLE tpc_trips
        MODIFY COLUMN status ENUM(
            'ASSIGNED',
            'ACTIVE',
            'PENDING_MANUAL_APPROVAL',
            'PENDING_APPROVAL',
            'PENDING_OFFICE_REVIEW',
            'PENDING_FINANCE_REVIEW',
            'COMPLETED',
            'CANCELLED'
        ) NOT NULL
    """)


def downgrade() -> None:
    # Any trip still waiting is treated as rejected so the old enum fits.
    op.execute(
        "UPDATE tpc_trips SET status = 'CANCELLED' "
        "WHERE status = 'PENDING_MANUAL_APPROVAL'"
    )
    op.execute("""
        ALTER TABLE tpc_trips
        MODIFY COLUMN status ENUM(
            'ASSIGNED',
            'ACTIVE',
            'PENDING_APPROVAL',
            'PENDING_OFFICE_REVIEW',
            'PENDING_FINANCE_REVIEW',
            'COMPLETED',
            'CANCELLED'
        ) NOT NULL
    """)
