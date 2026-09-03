"""added payment type in the expense model

Revision ID: 405e147ffc40
Revises: 41a95ef1e207
Create Date: 2026-08-31 13:48:42.389095

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '405e147ffc40'
down_revision: Union[str, Sequence[str], None] = '41a95ef1e207'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_finance_expenses",
        sa.Column(
            "payment_type",
            sa.String(length=20),
            nullable=False,
            server_default="PO",
        ),
    )

    # Remove the server-side default after existing
    # records have been populated with "PO".
    op.alter_column(
        "tpc_finance_expenses",
        "payment_type",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column(
        "tpc_finance_expenses",
        "payment_type",
    )