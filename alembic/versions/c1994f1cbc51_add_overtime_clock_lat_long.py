"""add overtime clock-in/out lat and long

Revision ID: c1994f1cbc51
Revises: c0e29d36f67a
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1994f1cbc51'
down_revision: Union[str, Sequence[str], None] = 'c0e29d36f67a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Best-effort location captured at clock-in/clock-out -- never
    # required, just recorded for the audit trail and the selfie
    # watermark's geofence label. See app/models/overtime_request.py.
    op.add_column(
        "tpc_overtime_requests",
        sa.Column("clock_in_lat", sa.Float(), nullable=True),
    )
    op.add_column(
        "tpc_overtime_requests",
        sa.Column("clock_in_long", sa.Float(), nullable=True),
    )
    op.add_column(
        "tpc_overtime_requests",
        sa.Column("clock_out_lat", sa.Float(), nullable=True),
    )
    op.add_column(
        "tpc_overtime_requests",
        sa.Column("clock_out_long", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tpc_overtime_requests", "clock_out_long")
    op.drop_column("tpc_overtime_requests", "clock_out_lat")
    op.drop_column("tpc_overtime_requests", "clock_in_long")
    op.drop_column("tpc_overtime_requests", "clock_in_lat")
