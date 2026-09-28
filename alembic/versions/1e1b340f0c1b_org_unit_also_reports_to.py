"""org unit also reports to

Revision ID: 1e1b340f0c1b
Revises: 0d8b77401746
Create Date: 2026-09-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e1b340f0c1b'
down_revision: Union[str, Sequence[str], None] = '0d8b77401746'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Extra parents for an org unit (JSON list of unit ids): the unit is
    drawn once under parent_id and linked from these."""
    op.add_column(
        'tpc_org_units', sa.Column('also_reports_to', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('tpc_org_units', 'also_reports_to')
