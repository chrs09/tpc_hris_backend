"""notifications: ref_id (e.g. the leave request a LEAVE_REQUESTED notice is about)

Revision ID: f6b8d0e2a415
Revises: e4a6c8d0f213
Create Date: 2026-10-08
"""

import sqlalchemy as sa
from alembic import op

revision = "f6b8d0e2a415"
down_revision = "e4a6c8d0f213"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_notifications", sa.Column("ref_id", sa.Integer(), nullable=True))
    op.create_index("ix_tpc_notifications_type_ref", "tpc_notifications", ["type", "ref_id"])


def downgrade():
    op.drop_index("ix_tpc_notifications_type_ref", table_name="tpc_notifications")
    op.drop_column("tpc_notifications", "ref_id")
