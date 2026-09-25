"""add trip remarks table

Revision ID: 62c290c89bd8
Revises: 2551058728aa
Create Date: 2026-09-25 16:08:55.261656

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '62c290c89bd8'
down_revision: Union[str, Sequence[str], None] = '2551058728aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Notes (text and/or image) added to a trip after approval."""
    op.create_table(
        'tpc_trip_remarks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['trip_id'], ['tpc_trips.id']),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['tpc_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tpc_trip_remarks_id'), 'tpc_trip_remarks', ['id'], unique=False)
    op.create_index(op.f('ix_tpc_trip_remarks_trip_id'), 'tpc_trip_remarks', ['trip_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tpc_trip_remarks_trip_id'), table_name='tpc_trip_remarks')
    op.drop_index(op.f('ix_tpc_trip_remarks_id'), table_name='tpc_trip_remarks')
    op.drop_table('tpc_trip_remarks')
