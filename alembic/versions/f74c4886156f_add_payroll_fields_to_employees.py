"""add payroll fields to employees

Revision ID: f74c4886156f
Revises: fdcf99ea6387
Create Date: 2026-05-28 16:18:22.305425

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'f74c4886156f'
down_revision: Union[str, Sequence[str], None] = 'fdcf99ea6387'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    op.add_column(
        'tpc_employees',
        sa.Column('daily_rate', sa.Numeric(10,2), nullable=True)
    )

    op.add_column(
        'tpc_employees',
        sa.Column('employment_type', sa.String(20), nullable=True)
    )

    op.add_column(
        'tpc_employees',
        sa.Column('payroll_type', sa.String(20), nullable=True)
    )


def downgrade():
    op.drop_column('tpc_employees', 'payroll_type')
    op.drop_column('tpc_employees', 'employment_type')
    op.drop_column('tpc_employees', 'daily_rate')