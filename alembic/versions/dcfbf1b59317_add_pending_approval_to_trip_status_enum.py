"""add pending approval to trip_status_enum

Revision ID: dcfbf1b59317
Revises: fe671760b626
Create Date: 2026-02-28 11:48:47.022214

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dcfbf1b59317"
down_revision: Union[str, Sequence[str], None] = "fe671760b626"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


"""add pending approval to trip_status_enum

Revision ID: dcfbf1b59317
Revises: fe671760b626
Create Date: 2026-02-28 11:48:47.022214

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "dcfbf1b59317"
down_revision: Union[str, Sequence[str], None] = "fe671760b626"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tpc_trips 
        MODIFY COLUMN status ENUM(
            'ASSIGNED',
            'ACTIVE',
            'PENDING_APPROVAL',
            'COMPLETED',
            'CANCELLED'
        ) NOT NULL
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE tpc_trips 
        MODIFY COLUMN status ENUM(
            'ASSIGNED',
            'ACTIVE',
            'COMPLETED',
            'CANCELLED'
        ) NOT NULL
    """)
