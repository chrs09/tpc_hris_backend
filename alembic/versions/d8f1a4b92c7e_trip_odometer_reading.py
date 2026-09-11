"""trip odometer reading

Revision ID: d8f1a4b92c7e
Revises: c4d8e2f76a91
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8f1a4b92c7e"
down_revision: Union[str, Sequence[str], None] = "c4d8e2f76a91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tpc_trips",
        sa.Column("odometer_reading", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tpc_trips", "odometer_reading")
