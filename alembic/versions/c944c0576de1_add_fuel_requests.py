"""add fuel requests

Revision ID: c944c0576de1
Revises: eba8f5c29516
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c944c0576de1'
down_revision: Union[str, Sequence[str], None] = 'eba8f5c29516'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Driver fuel requests (mobile Fuel tab, web Fuel Requests page)."""
    op.create_table(
        'tpc_fuel_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=True),
        sa.Column('plate_number', sa.String(length=50), nullable=False),
        sa.Column('city', sa.String(length=120), nullable=False),
        sa.Column('odo_photo_url', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('fuel_code', sa.String(length=100), nullable=True),
        sa.Column('liters', sa.Numeric(10, 2), nullable=True),
        sa.Column('issued_by_user_id', sa.Integer(), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=True),
        sa.Column('receipt_photo_url', sa.String(length=500), nullable=True),
        sa.Column('receipt_submitted_at', sa.DateTime(), nullable=True),
        sa.Column('completed_by_user_id', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['tpc_users.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['tpc_employees.id']),
        sa.ForeignKeyConstraint(['issued_by_user_id'], ['tpc_users.id']),
        sa.ForeignKeyConstraint(['completed_by_user_id'], ['tpc_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tpc_fuel_requests_id'), 'tpc_fuel_requests', ['id'])
    op.create_index(op.f('ix_tpc_fuel_requests_user_id'), 'tpc_fuel_requests', ['user_id'])
    op.create_index(op.f('ix_tpc_fuel_requests_status'), 'tpc_fuel_requests', ['status'])


def downgrade() -> None:
    op.drop_index(op.f('ix_tpc_fuel_requests_status'), table_name='tpc_fuel_requests')
    op.drop_index(op.f('ix_tpc_fuel_requests_user_id'), table_name='tpc_fuel_requests')
    op.drop_index(op.f('ix_tpc_fuel_requests_id'), table_name='tpc_fuel_requests')
    op.drop_table('tpc_fuel_requests')
