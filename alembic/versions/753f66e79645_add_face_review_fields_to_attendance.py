"""add face review fields to attendance

Revision ID: 753f66e79645
Revises: 5d7009c57bbe
Create Date: 2026-05-22 15:55:34.387203

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "753f66e79645"
down_revision: Union[str, Sequence[str], None] = "5d7009c57bbe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "tpc_attendance_records",
        sa.Column("face_match_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "tpc_attendance_records",
        sa.Column("face_review_status", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "tpc_attendance_records",
        sa.Column("face_review_reason", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "tpc_attendance_records",
        sa.Column("face_checked_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "tpc_attendance_records",
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tpc_attendance_records", sa.Column("reviewed_at", sa.DateTime(), nullable=True)
    )


def downgrade():
    op.drop_column("tpc_attendance_records", "reviewed_at")
    op.drop_column("tpc_attendance_records", "reviewed_by_user_id")
    op.drop_column("tpc_attendance_records", "face_checked_at")
    op.drop_column("tpc_attendance_records", "face_review_reason")
    op.drop_column("tpc_attendance_records", "face_review_status")
    op.drop_column("tpc_attendance_records", "face_match_score")
