"""add error logs table

Revision ID: c5af81c5f70d
Revises: f8bc4ffbfdd6
Create Date: 2026-09-12 14:53:15.514920

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5af81c5f70d'
down_revision: Union[str, Sequence[str], None] = 'f8bc4ffbfdd6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tpc_error_logs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_tpc_error_logs_created_at",
        "tpc_error_logs",
        ["created_at"],
    )
    # Note: the `id` column's index=True already creates its own index
    # as part of create_table above -- no separate op.create_index needed
    # (doing so duplicates it and MySQL rejects the second one).


def downgrade() -> None:
    op.drop_index("ix_tpc_error_logs_created_at", table_name="tpc_error_logs")
    op.drop_table("tpc_error_logs")
