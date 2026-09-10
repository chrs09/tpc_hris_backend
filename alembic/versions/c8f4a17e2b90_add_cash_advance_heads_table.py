"""add cash advance heads table

Revision ID: c8f4a17e2b90
Revises: b7c3d9e14f52
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8f4a17e2b90'
down_revision: Union[str, Sequence[str], None] = 'b7c3d9e14f52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tpc_cash_advance_heads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("department", sa.String(length=50), nullable=False),
        sa.Column("head_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["head_user_id"], ["tpc_users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["tpc_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("department"),
    )
    op.create_index(
        op.f("ix_tpc_cash_advance_heads_id"),
        "tpc_cash_advance_heads",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tpc_cash_advance_heads_department"),
        "tpc_cash_advance_heads",
        ["department"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tpc_cash_advance_heads_department"),
        table_name="tpc_cash_advance_heads",
    )
    op.drop_index(
        op.f("ix_tpc_cash_advance_heads_id"), table_name="tpc_cash_advance_heads"
    )
    op.drop_table("tpc_cash_advance_heads")
