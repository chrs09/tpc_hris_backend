"""attendance: missed time out (filed the next time in, approved by the head)

Revision ID: c9e1a3b5d748
Revises: b8d0f2a4c637
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

revision = "c9e1a3b5d748"
down_revision = "b8d0f2a4c637"
branch_labels = None
depends_on = None

TABLE = "tpc_attendance_records"


def upgrade():
    op.add_column(TABLE, sa.Column("missed_out_requested_at", sa.DateTime(), nullable=True))
    op.add_column(TABLE, sa.Column("missed_out_reason", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("missed_out_filed_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column(TABLE, "missed_out_filed_at")
    op.drop_column(TABLE, "missed_out_reason")
    op.drop_column(TABLE, "missed_out_requested_at")
