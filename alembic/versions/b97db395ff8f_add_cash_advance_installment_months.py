"""add cash advance installment months

Revision ID: b97db395ff8f
Revises: e035ad757d2c
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b97db395ff8f'
down_revision: Union[str, Sequence[str], None] = 'e035ad757d2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # How many months the approved amount is split into for deduction --
    # proposed by the driver, adjustable by the approving head. Tracked/
    # displayed only for now, not yet wired into payslip generation.
    op.add_column(
        "tpc_cash_advance_requests",
        sa.Column(
            "installment_months",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("tpc_cash_advance_requests", "installment_months")
