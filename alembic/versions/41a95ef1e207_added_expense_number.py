"""added expense number

Revision ID: 41a95ef1e207
Revises: 26f6566d8fd0
Create Date: 2026-08-21 14:51:44.925327

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "41a95ef1e207"
down_revision: Union[str, Sequence[str], None] = "26f6566d8fd0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "tpc_finance_expenses",
        sa.Column(
            "expense_number",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_tpc_finance_expenses_expense_number",
        "tpc_finance_expenses",
        ["expense_number"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_tpc_finance_expenses_expense_number",
        table_name="tpc_finance_expenses",
    )

    op.drop_column(
        "tpc_finance_expenses",
        "expense_number",
    )