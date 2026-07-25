"""add required_helper and profile to stores

Revision ID: 202607170621
Revises: fe671760b626
Create Date: 2026-07-17 06:21:06.756494
"""

from alembic import op
import sqlalchemy as sa

revision = '202607170621'
down_revision = '7365d2fc3fbe'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tpc_stores', sa.Column('required_helper', sa.Integer(), nullable=False, server_default='0'))
    op.add_column(
        'tpc_stores',
        sa.Column(
            'profile',
            sa.String(50),
            nullable=False,
            server_default='DP',
        ),
    )


def downgrade() -> None:
    op.drop_column('tpc_stores', 'profile')
    op.drop_column('tpc_stores', 'required_helper')
    op.drop_column('tpc_stores', 'profile')
    op.drop_column('tpc_stores', 'required_helper')
