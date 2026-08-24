"""add finance item model

Revision ID: 26f6566d8fd0
Revises: 355ec343c98b
Create Date: 2026-08-21 14:22:56.496500

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "26f6566d8fd0"
down_revision: Union[str, Sequence[str], None] = "355ec343c98b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "tpc_finance_expense_items",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "expense_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "particulars",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "qty",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="1",
        ),

        sa.Column(
            "unit",
            sa.String(length=50),
            nullable=True,
        ),

        sa.Column(
            "unit_price",
            sa.Numeric(14, 2),
            nullable=True,
        ),

        sa.Column(
            "amount",
            sa.Numeric(14, 2),
            nullable=True,
        ),

        sa.ForeignKeyConstraint(
            ["expense_id"],
            ["tpc_finance_expenses.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_tpc_finance_expense_items_id"),
        "tpc_finance_expense_items",
        ["id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_tpc_finance_expense_items_expense_id"),
        "tpc_finance_expense_items",
        ["expense_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f("ix_tpc_finance_expense_items_expense_id"),
        table_name="tpc_finance_expense_items",
    )

    op.drop_index(
        op.f("ix_tpc_finance_expense_items_id"),
        table_name="tpc_finance_expense_items",
    )

    op.drop_table("tpc_finance_expense_items")