"""convert_profile_enum_to_varchar

Revision ID: 140f22620bd2
Revises: 202607170621
Create Date: 2026-07-17 15:08:49.892563

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '140f22620bd2'
down_revision: Union[str, Sequence[str], None] = '202607170621'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop the ENUM constraint and recreate as VARCHAR
    op.execute("ALTER TABLE tpc_stores MODIFY COLUMN profile VARCHAR(50) NOT NULL DEFAULT 'Core A - No Helper'")


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate as ENUM
    op.execute("""
        ALTER TABLE tpc_stores 
        MODIFY COLUMN profile ENUM(
            'Core A - No Helper',
            'Core B - No Helper', 
            'Key Accounts',
            'Core C - No Helper',
            'Wholesaler'
        ) NOT NULL DEFAULT 'Core A - No Helper'
    """)
