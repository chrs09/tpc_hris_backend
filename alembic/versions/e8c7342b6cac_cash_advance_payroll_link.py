"""cash advance payroll link

Revision ID: e8c7342b6cac
Revises: 62c290c89bd8
Create Date: 2026-09-25 16:24:52.770768

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8c7342b6cac'
down_revision: Union[str, Sequence[str], None] = '62c290c89bd8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Payroll records the cutoff's cash advance deduction, and each
    cash advance deduction entry remembers which cutoff posted it."""
    op.add_column(
        'payroll_deductions',
        sa.Column(
            'cash_advance_deduction',
            sa.Numeric(12, 2),
            nullable=False,
            server_default='0',
        ),
    )
    op.add_column(
        'tpc_cash_advance_deduction_logs',
        sa.Column('payroll_cutoff_period', sa.String(length=50), nullable=True),
    )
    op.create_index(
        op.f('ix_tpc_cash_advance_deduction_logs_payroll_cutoff_period'),
        'tpc_cash_advance_deduction_logs',
        ['payroll_cutoff_period'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_tpc_cash_advance_deduction_logs_payroll_cutoff_period'),
        table_name='tpc_cash_advance_deduction_logs',
    )
    op.drop_column('tpc_cash_advance_deduction_logs', 'payroll_cutoff_period')
    op.drop_column('payroll_deductions', 'cash_advance_deduction')
