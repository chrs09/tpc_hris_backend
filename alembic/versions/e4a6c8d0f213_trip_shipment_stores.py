"""trip shipment stores: which store each shipment number goes to

Revision ID: e4a6c8d0f213
Revises: d1f3b5c7e902
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from alembic import op

revision = "e4a6c8d0f213"
down_revision = "d1f3b5c7e902"
branch_labels = None
depends_on = None


def upgrade():
    # JSON {"<shipment no>": <store id>} set at dispatch; shown per stop
    # in Trip Review.
    op.add_column("tpc_trips", sa.Column("shipment_stores", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("tpc_trips", "shipment_stores")
