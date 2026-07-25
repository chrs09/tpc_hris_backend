"""update_store_profile_values_to_codes

Revision ID: f76d8c534f57
Revises: 140f22620bd2
Create Date: 2026-07-17 15:19:10.877417

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f76d8c534f57'
down_revision: Union[str, Sequence[str], None] = '140f22620bd2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - convert profile values to codes."""
    op.execute("UPDATE tpc_stores SET profile = 'DP' WHERE profile = 'Core A - No Helper'")
    op.execute("UPDATE tpc_stores SET profile = 'KD' WHERE profile = 'Core B - No Helper'")
    op.execute("UPDATE tpc_stores SET profile = 'KA' WHERE profile = 'Key Accounts'")
    op.execute("UPDATE tpc_stores SET profile = 'PUP' WHERE profile = 'Core C - No Helper'")
    op.execute("UPDATE tpc_stores SET profile = 'WS' WHERE profile = 'Wholesaler'")


def downgrade() -> None:
    """Downgrade schema - revert profile values back to full names."""
    op.execute("UPDATE tpc_stores SET profile = 'Core A - No Helper' WHERE profile = 'DP'")
    op.execute("UPDATE tpc_stores SET profile = 'Core B - No Helper' WHERE profile = 'KD'")
    op.execute("UPDATE tpc_stores SET profile = 'Key Accounts' WHERE profile = 'KA'")
    op.execute("UPDATE tpc_stores SET profile = 'Core C - No Helper' WHERE profile = 'PUP'")
    op.execute("UPDATE tpc_stores SET profile = 'Wholesaler' WHERE profile = 'WS'")

