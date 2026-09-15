"""add tickets table

Revision ID: f7b78c6649a3
Revises: d7696d6f6e32
Create Date: 2026-09-15 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7b78c6649a3'
down_revision: Union[str, Sequence[str], None] = 'd7696d6f6e32'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tpc_tickets",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="todo"),
        sa.Column("priority", sa.String(length=10), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("tpc_users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_tpc_tickets_status", "tpc_tickets", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tpc_tickets_status", table_name="tpc_tickets")
    op.drop_table("tpc_tickets")
