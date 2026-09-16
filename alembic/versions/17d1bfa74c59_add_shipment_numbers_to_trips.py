"""add shipment_numbers to trips, widen ticket_no

Revision ID: 17d1bfa74c59
Revises: d4e9a1f6b2c8
Create Date: 2026-09-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "17d1bfa74c59"
down_revision = "d4e9a1f6b2c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tpc_trips",
        sa.Column("shipment_numbers", sa.Text(), nullable=True),
    )
    op.alter_column(
        "tpc_trips",
        "ticket_no",
        existing_type=sa.String(100),
        type_=sa.String(500),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "tpc_trips",
        "ticket_no",
        existing_type=sa.String(500),
        type_=sa.String(100),
        existing_nullable=True,
    )
    op.drop_column("tpc_trips", "shipment_numbers")
