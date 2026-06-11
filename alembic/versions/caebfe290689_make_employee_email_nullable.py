"""make employee email nullable

Revision ID: caebfe290689
Revises: a7380fa16ad0
Create Date: 2026-06-11 12:09:14.654384

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'caebfe290689'
down_revision: Union[str, Sequence[str], None] = 'a7380fa16ad0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "tpc_employees",
        "email",
        existing_type=sa.String(length=100),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "tpc_employees",
        "email",
        existing_type=sa.String(length=100),
        nullable=False,
    )