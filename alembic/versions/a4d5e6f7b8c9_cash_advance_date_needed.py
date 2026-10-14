"""cash advance request: date needed (when the driver needs the money)

Revision ID: a4d5e6f7b8c9
Revises: f3c4d5e6a7b8
Create Date: 2026-10-14
"""

import sqlalchemy as sa
from alembic import op

revision = "a4d5e6f7b8c9"
down_revision = "f3c4d5e6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_cash_advance_requests", sa.Column("date_needed", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("tpc_cash_advance_requests", "date_needed")
