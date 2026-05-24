"""added time in/out in attendance

Revision ID: 4e55873c7e5c
Revises: 45540415d320
Create Date: 2026-05-14 15:36:04.351985
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "4e55873c7e5c"
down_revision: Union[str, Sequence[str], None] = "45540415d320"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================
    # TIME IN
    # =========================
    op.add_column(
        "tpc_attendance_records",
        sa.Column("time_in_latitude", sa.Float(), nullable=True),
    )

    op.add_column(
        "tpc_attendance_records",
        sa.Column("time_in_longitude", sa.Float(), nullable=True),
    )

    op.add_column(
        "tpc_attendance_records",
        sa.Column("time_in_address", sa.String(length=500), nullable=True),
    )

    # =========================
    # TIME OUT
    # =========================
    op.add_column(
        "tpc_attendance_records",
        sa.Column("check_out_time", sa.DateTime(), nullable=True),
    )

    op.add_column(
        "tpc_attendance_records",
        sa.Column("time_out_latitude", sa.Float(), nullable=True),
    )

    op.add_column(
        "tpc_attendance_records",
        sa.Column("time_out_longitude", sa.Float(), nullable=True),
    )

    op.add_column(
        "tpc_attendance_records",
        sa.Column("time_out_address", sa.String(length=500), nullable=True),
    )

    # =========================
    # OPTIONAL
    # =========================
    op.add_column(
        "tpc_attendance_records",
        sa.Column("attendance_method", sa.String(length=30), nullable=True),
    )

    op.add_column(
        "tpc_attendance_records",
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # =========================
    # MODIFY EXISTING
    # =========================
    op.alter_column(
        "tpc_attendance_records",
        "check_in_time",
        existing_type=sa.DateTime(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "tpc_attendance_records",
        "check_in_time",
        existing_type=sa.DateTime(),
        nullable=False,
    )

    op.drop_column("tpc_attendance_records", "created_at")
    op.drop_column("tpc_attendance_records", "attendance_method")

    op.drop_column("tpc_attendance_records", "time_out_address")
    op.drop_column("tpc_attendance_records", "time_out_longitude")
    op.drop_column("tpc_attendance_records", "time_out_latitude")
    op.drop_column("tpc_attendance_records", "check_out_time")

    op.drop_column("tpc_attendance_records", "time_in_address")
    op.drop_column("tpc_attendance_records", "time_in_longitude")
    op.drop_column("tpc_attendance_records", "time_in_latitude")
