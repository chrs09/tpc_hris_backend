"""add cr/or fields to vehicle units

Revision ID: b7e1a2c9f4d6
Revises: a1c4f9d2e7b3
Create Date: 2026-09-16 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e1a2c9f4d6'
down_revision: Union[str, Sequence[str], None] = 'a1c4f9d2e7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_vehicle_units",
        sa.Column("cr_or_number", sa.String(100), nullable=True),
    )
    op.add_column(
        "tpc_vehicle_units",
        sa.Column("cr_or_document_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "tpc_vehicle_units",
        sa.Column("cr_or_expiration_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tpc_vehicle_units", "cr_or_expiration_date")
    op.drop_column("tpc_vehicle_units", "cr_or_document_url")
    op.drop_column("tpc_vehicle_units", "cr_or_number")
