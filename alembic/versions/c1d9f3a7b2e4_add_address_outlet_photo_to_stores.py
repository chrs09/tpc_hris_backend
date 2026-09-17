"""add address, outlet_number, photo_url to stores

Revision ID: c1d9f3a7b2e4
Revises: b8f4d6c2a9e1
Create Date: 2026-09-17 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1d9f3a7b2e4"
down_revision = "b8f4d6c2a9e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tpc_stores", sa.Column("address", sa.String(255), nullable=True))
    op.add_column("tpc_stores", sa.Column("outlet_number", sa.String(50), nullable=True))
    op.add_column("tpc_stores", sa.Column("photo_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("tpc_stores", "photo_url")
    op.drop_column("tpc_stores", "outlet_number")
    op.drop_column("tpc_stores", "address")
