"""add cash advance purposes and max active requests

Revision ID: ced3b747c55b
Revises: 46199763822b
Create Date: 2026-09-24 14:56:58.394338

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ced3b747c55b'
down_revision: Union[str, Sequence[str], None] = '46199763822b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tpc_cash_advance_terms",
        sa.Column("max_active_requests", sa.Integer(), nullable=True),
    )

    op.create_table(
        "tpc_cash_advance_purposes",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("label", sa.String(length=150), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("tpc_cash_advance_purposes")
    op.drop_column("tpc_cash_advance_terms", "max_active_requests")
