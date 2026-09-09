"""add cash advance max pay periods

Revision ID: a4e8f2c91b3d
Revises: 770fca07ca9f
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4e8f2c91b3d'
down_revision: Union[str, Sequence[str], None] = '770fca07ca9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_cash_advance_terms",
        sa.Column(
            "max_pay_periods",
            sa.Integer(),
            nullable=False,
            server_default="6",
        ),
    )
    op.alter_column(
        "tpc_cash_advance_terms", "max_pay_periods", server_default=None
    )


def downgrade() -> None:
    op.drop_column("tpc_cash_advance_terms", "max_pay_periods")
