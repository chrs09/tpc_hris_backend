"""merge alembic heads

Revision ID: 30a55dfc642e
Revises: d8f1a4b92c7e, d92e6a3f18c4
Create Date: 2026-09-11 11:14:45.582101

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '30a55dfc642e'
down_revision: Union[str, Sequence[str], None] = ('d8f1a4b92c7e', 'd92e6a3f18c4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
