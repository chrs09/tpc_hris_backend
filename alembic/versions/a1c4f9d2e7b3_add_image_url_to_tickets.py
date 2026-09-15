"""add image_url to tickets

Revision ID: a1c4f9d2e7b3
Revises: 3324c4241493
Create Date: 2026-09-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c4f9d2e7b3'
down_revision: Union[str, Sequence[str], None] = '3324c4241493'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_tickets",
        sa.Column("image_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tpc_tickets", "image_url")
