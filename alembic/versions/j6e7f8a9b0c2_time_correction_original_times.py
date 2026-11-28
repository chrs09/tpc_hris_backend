"""Time correction: the times the attendance showed when it was filed

Revision ID: j6e7f8a9b0c2
Revises: i5d6e7f8a9b1
Create Date: 2026-11-28
"""

import sqlalchemy as sa
from alembic import op

revision = "j6e7f8a9b0c2"
down_revision = "i5d6e7f8a9b1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_time_corrections", sa.Column("original_time_in", sa.DateTime(), nullable=True))
    op.add_column("tpc_time_corrections", sa.Column("original_time_out", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("tpc_time_corrections", "original_time_out")
    op.drop_column("tpc_time_corrections", "original_time_in")
