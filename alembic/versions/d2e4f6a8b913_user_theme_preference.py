"""user theme preference

Each user's own theme (light/dark/system + accent colour), so it follows
them on every device.

Revision ID: d2e4f6a8b913
Revises: c7d9e1f3a524
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "d2e4f6a8b913"
down_revision = "c7d9e1f3a524"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_users", sa.Column("theme_preference", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("tpc_users", "theme_preference")
