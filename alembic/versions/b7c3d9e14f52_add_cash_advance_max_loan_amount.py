"""add cash advance max loan amount

Revision ID: b7c3d9e14f52
Revises: a4e8f2c91b3d
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c3d9e14f52'
down_revision: Union[str, Sequence[str], None] = 'a4e8f2c91b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_cash_advance_terms",
        sa.Column("max_loan_amount", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tpc_cash_advance_terms", "max_loan_amount")
