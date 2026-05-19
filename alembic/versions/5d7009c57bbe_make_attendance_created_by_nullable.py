"""make attendance created_by nullable

Revision ID: 5d7009c57bbe
Revises: 4e55873c7e5c
Create Date: 2026-05-18 15:29:27.922603

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d7009c57bbe'
down_revision: Union[str, Sequence[str], None] = '4e55873c7e5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.alter_column(
        "tpc_attendance_records",
        "created_by_user_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade():
    op.alter_column(
        "tpc_attendance_records",
        "created_by_user_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
