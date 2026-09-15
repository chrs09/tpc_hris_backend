"""add user id and username to error logs

Revision ID: d7696d6f6e32
Revises: 959efe980feb
Create Date: 2026-09-15 10:08:39.780621

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7696d6f6e32'
down_revision: Union[str, Sequence[str], None] = '959efe980feb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_error_logs",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tpc_error_logs",
        sa.Column("username", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_tpc_error_logs_user_id",
        "tpc_error_logs",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tpc_error_logs_user_id", table_name="tpc_error_logs")
    op.drop_column("tpc_error_logs", "username")
    op.drop_column("tpc_error_logs", "user_id")
