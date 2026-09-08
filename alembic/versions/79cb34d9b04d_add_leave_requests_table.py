"""add leave requests table

Revision ID: 79cb34d9b04d
Revises: 405e147ffc40
Create Date: 2026-09-07 11:08:01.679228

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '79cb34d9b04d'
down_revision: Union[str, Sequence[str], None] = '405e147ffc40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tpc_leave_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('leave_type', sa.String(length=30), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('review_remarks', sa.Text(), nullable=True),
        sa.Column('reviewed_by_user_id', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['tpc_employees.id']),
        sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['tpc_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_tpc_leave_requests_id'),
        'tpc_leave_requests',
        ['id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_tpc_leave_requests_id'),
        table_name='tpc_leave_requests',
    )
    op.drop_table('tpc_leave_requests')
