"""ticket comments

Revision ID: 0f0774d1e572
Revises: a268343d1c91
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f0774d1e572'
down_revision: Union[str, Sequence[str], None] = 'a268343d1c91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Comments/remarks on tickets."""
    op.create_table(
        'tpc_ticket_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['tpc_tickets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['tpc_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tpc_ticket_comments_id'), 'tpc_ticket_comments', ['id'])
    op.create_index(
        op.f('ix_tpc_ticket_comments_ticket_id'), 'tpc_ticket_comments', ['ticket_id']
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_tpc_ticket_comments_ticket_id'), table_name='tpc_ticket_comments')
    op.drop_index(op.f('ix_tpc_ticket_comments_id'), table_name='tpc_ticket_comments')
    op.drop_table('tpc_ticket_comments')
