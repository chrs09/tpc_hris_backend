"""add is_available column in vehicle unit

Revision ID: df532f429f96
Revises: b15d7ae6cb49
Create Date: 2026-06-15 09:01:38.500144

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "df532f429f96"
down_revision: Union[str, Sequence[str], None] = "b15d7ae6cb49"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "tpc_vehicle_units",
        sa.Column("is_available", sa.Boolean(), nullable=False, default=True),
    )


def downgrade():
    op.drop_column("tpc_vehicle_units", "is_available")
