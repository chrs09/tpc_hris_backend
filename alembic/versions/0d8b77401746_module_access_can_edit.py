"""module access can edit

Revision ID: 0d8b77401746
Revises: 265796f25e3e
Create Date: 2026-09-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d8b77401746'
down_revision: Union[str, Sequence[str], None] = '265796f25e3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Per-grant "can edit": False = view-only for that module (changes
    are refused). Existing grants stay editable."""
    op.add_column(
        'tpc_employee_module_access',
        sa.Column('can_edit', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column('tpc_employee_module_access', 'can_edit')
