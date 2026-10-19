"""photo seals: reference code + SHA-256 + time/GPS of every stamped
photo (Administrator -> Verify Photo)

Revision ID: d7a8b9c0e1f2
Revises: c6f7a8b9d0e1
Create Date: 2026-10-19
"""

import sqlalchemy as sa
from alembic import op

revision = "d7a8b9c0e1f2"
down_revision = "c6f7a8b9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_photo_seals",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("ref", sa.String(20), nullable=False, unique=True, index=True),
        sa.Column("sha256", sa.String(64), nullable=False, index=True),
        sa.Column("file_url", sa.String(500), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("tpc_photo_seals")
