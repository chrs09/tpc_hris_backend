"""time corrections: time in / time out proof photos

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_time_corrections",
        sa.Column("time_in_photo_url", sa.String(1000), nullable=True),
    )
    op.add_column(
        "tpc_time_corrections",
        sa.Column("time_out_photo_url", sa.String(1000), nullable=True),
    )


def downgrade():
    op.drop_column("tpc_time_corrections", "time_out_photo_url")
    op.drop_column("tpc_time_corrections", "time_in_photo_url")
