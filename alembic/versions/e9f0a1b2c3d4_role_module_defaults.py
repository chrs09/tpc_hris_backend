"""role module defaults: the modules each role gets by default (Role Access)

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_role_module_defaults",
        sa.Column("role", sa.String(50), primary_key=True),
        sa.Column("module_keys", sa.Text(), nullable=False),
        sa.Column("read_only_keys", sa.Text(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("tpc_role_module_defaults")
