"""add assigned_to_user_id to tickets

Revision ID: 3324c4241493
Revises: f7b78c6649a3
Create Date: 2026-09-15 11:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3324c4241493'
down_revision: Union[str, Sequence[str], None] = 'f7b78c6649a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_tickets",
        sa.Column(
            "assigned_to_user_id",
            sa.Integer(),
            sa.ForeignKey("tpc_users.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_tpc_tickets_assigned_to_user_id",
        "tpc_tickets",
        ["assigned_to_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tpc_tickets_assigned_to_user_id", table_name="tpc_tickets"
    )
    op.drop_column("tpc_tickets", "assigned_to_user_id")
