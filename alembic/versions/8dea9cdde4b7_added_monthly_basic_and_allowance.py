"""added monthly basic and allowance

Revision ID: 8dea9cdde4b7
Revises: 1b771e824088
Create Date: 2026-07-30 13:52:33.560100

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8dea9cdde4b7'
down_revision: Union[str, Sequence[str], None] = '1b771e824088'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_employees",
        sa.Column("monthly_basic", sa.Numeric(10, 2), nullable=True),
    )

    op.add_column(
        "tpc_employees",
        sa.Column("monthly_allow", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tpc_employees", "monthly_allow")
    op.drop_column("tpc_employees", "monthly_basic")
