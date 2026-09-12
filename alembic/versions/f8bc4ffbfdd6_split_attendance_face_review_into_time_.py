"""split attendance face review into time in and time out

Revision ID: f8bc4ffbfdd6
Revises: 30a55dfc642e
Create Date: 2026-09-12 14:18:04.784585

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8bc4ffbfdd6'
down_revision: Union[str, Sequence[str], None] = '30a55dfc642e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Face review has only ever run for time-in (see check-out never
    calling FaceRecognitionService in app/api/attendance.py) -- these
    existing columns are renamed with a time_in_ prefix so they keep
    their history, and a mirrored set of time_out_ columns is added so
    time-out can now get the same verification/review treatment
    independently."""
    op.alter_column(
        "tpc_attendance_records",
        "face_match_score",
        new_column_name="time_in_face_match_score",
        existing_type=sa.Float(),
        existing_nullable=True,
    )
    op.alter_column(
        "tpc_attendance_records",
        "face_review_status",
        new_column_name="time_in_face_review_status",
        existing_type=sa.String(length=50),
        existing_nullable=True,
    )
    op.alter_column(
        "tpc_attendance_records",
        "face_review_reason",
        new_column_name="time_in_face_review_reason",
        existing_type=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "tpc_attendance_records",
        "face_checked_at",
        new_column_name="time_in_face_checked_at",
        existing_type=sa.DateTime(),
        existing_nullable=True,
    )

    op.add_column(
        "tpc_attendance_records",
        sa.Column("time_out_face_match_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "tpc_attendance_records",
        sa.Column(
            "time_out_face_review_status", sa.String(length=50), nullable=True
        ),
    )
    op.add_column(
        "tpc_attendance_records",
        sa.Column("time_out_face_review_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "tpc_attendance_records",
        sa.Column("time_out_face_checked_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tpc_attendance_records", "time_out_face_checked_at")
    op.drop_column("tpc_attendance_records", "time_out_face_review_reason")
    op.drop_column("tpc_attendance_records", "time_out_face_review_status")
    op.drop_column("tpc_attendance_records", "time_out_face_match_score")

    op.alter_column(
        "tpc_attendance_records",
        "time_in_face_checked_at",
        new_column_name="face_checked_at",
        existing_type=sa.DateTime(),
        existing_nullable=True,
    )
    op.alter_column(
        "tpc_attendance_records",
        "time_in_face_review_reason",
        new_column_name="face_review_reason",
        existing_type=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "tpc_attendance_records",
        "time_in_face_review_status",
        new_column_name="face_review_status",
        existing_type=sa.String(length=50),
        existing_nullable=True,
    )
    op.alter_column(
        "tpc_attendance_records",
        "time_in_face_match_score",
        new_column_name="face_match_score",
        existing_type=sa.Float(),
        existing_nullable=True,
    )
