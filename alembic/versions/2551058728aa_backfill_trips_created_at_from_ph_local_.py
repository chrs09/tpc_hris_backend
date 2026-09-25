"""backfill trips created_at from PH local to utc

Revision ID: 2551058728aa
Revises: ac47c8ba5fee
Create Date: 2026-09-25 09:28:43.685567

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2551058728aa'
down_revision: Union[str, Sequence[str], None] = 'ac47c8ba5fee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# tpc_trips.created_at used MySQL's NOW() as a server default, which on this
# deployment returns PH local time (UTC+8), but every reader treats the
# column as UTC and converts to PH again -- so every existing trip's
# "Dispatched At" displayed 8 hours late (UTC+16 in total). The model now
# sets created_at from datetime.utcnow(); this shifts the rows created
# under the old default back to real UTC, once. The cutoff is the moment
# the model fix landed, so trips created after it (already UTC) are left
# alone.
_FIX_CUTOFF = "2026-09-24 13:26:00"


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            "UPDATE tpc_trips SET created_at = DATE_SUB(created_at, "
            "INTERVAL 8 HOUR) WHERE created_at < :cutoff"
        ).bindparams(cutoff=_FIX_CUTOFF)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text(
            "UPDATE tpc_trips SET created_at = DATE_ADD(created_at, "
            "INTERVAL 8 HOUR) WHERE created_at < DATE_SUB(:cutoff, "
            "INTERVAL 8 HOUR)"
        ).bindparams(cutoff=_FIX_CUTOFF)
    )
