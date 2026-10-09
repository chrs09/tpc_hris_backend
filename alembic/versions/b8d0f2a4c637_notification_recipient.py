"""notifications: recipient_user_id (a notice for one person, e.g. a head)

Revision ID: b8d0f2a4c637
Revises: a7c9e1f3b526
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

revision = "b8d0f2a4c637"
down_revision = "a7c9e1f3b526"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_notifications", sa.Column("recipient_user_id", sa.Integer(), nullable=True))
    op.create_index("ix_tpc_notifications_recipient", "tpc_notifications", ["recipient_user_id"])


def downgrade():
    op.drop_index("ix_tpc_notifications_recipient", table_name="tpc_notifications")
    op.drop_column("tpc_notifications", "recipient_user_id")
