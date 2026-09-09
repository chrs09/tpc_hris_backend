"""add started_outside_hub_range flag to trips

Revision ID: 0251470ba847
Revises: 27f1cf9da89f
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0251470ba847'
down_revision: Union[str, Sequence[str], None] = '27f1cf9da89f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_trips",
        sa.Column(
            "started_outside_hub_range",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("tpc_trips", "started_outside_hub_range")
