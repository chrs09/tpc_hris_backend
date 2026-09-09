"""add department heads table

Revision ID: d285bdb09102
Revises: e6b34f893133
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd285bdb09102'
down_revision: Union[str, Sequence[str], None] = 'e6b34f893133'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reporting hierarchy: which user is the immediate head of a given
    # employee department. See app/models/department_head.py.
    op.create_table(
        "tpc_department_heads",
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
        op.f("ix_tpc_department_heads_id"),
        "tpc_department_heads",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tpc_department_heads_department"),
        "tpc_department_heads",
        ["department"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tpc_department_heads_department"),
        table_name="tpc_department_heads",
    )
    op.drop_index(
        op.f("ix_tpc_department_heads_id"), table_name="tpc_department_heads"
    )
    op.drop_table("tpc_department_heads")
