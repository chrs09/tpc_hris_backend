"""add approved amount and release info to cash advance

Revision ID: ac47c8ba5fee
Revises: ced3b747c55b
Create Date: 2026-09-24 16:41:51.474837

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac47c8ba5fee'
down_revision: Union[str, Sequence[str], None] = 'ced3b747c55b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tpc_cash_advance_requests",
        sa.Column("approved_amount", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "tpc_cash_advance_requests",
        sa.Column("release_reference", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "tpc_cash_advance_requests",
        sa.Column("released_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "tpc_cash_advance_requests",
        sa.Column("released_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_tpc_cash_advance_requests_released_by",
        "tpc_cash_advance_requests",
        "tpc_users",
        ["released_by_user_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "fk_tpc_cash_advance_requests_released_by",
        "tpc_cash_advance_requests",
        type_="foreignkey",
    )
    op.drop_column("tpc_cash_advance_requests", "released_by_user_id")
    op.drop_column("tpc_cash_advance_requests", "released_at")
    op.drop_column("tpc_cash_advance_requests", "release_reference")
    op.drop_column("tpc_cash_advance_requests", "approved_amount")
