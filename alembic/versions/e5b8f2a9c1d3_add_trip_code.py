"""add trip code

Revision ID: e5b8f2a9c1d3
Revises: d92e6a3f18c4
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b8f2a9c1d3'
down_revision: Union[str, Sequence[str], None] = 'd92e6a3f18c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_trips", sa.Column("trip_code", sa.String(length=20), nullable=True)
    )
    op.create_index(
        op.f("ix_tpc_trips_trip_code"), "tpc_trips", ["trip_code"], unique=True
    )

    # Backfill existing trips so every trip has a code, not just ones
    # created after this migration. Codes are assigned in start_time
    # order, grouped by PH-local (UTC+8) calendar month, matching how
    # _generate_trip_code() in app/api/driver/trips.py assigns them
    # going forward.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, start_time FROM tpc_trips ORDER BY start_time ASC")
    ).fetchall()

    from datetime import timedelta

    counters = {}
    for row in rows:
        if row.start_time is None:
            continue
        # Compute the PH-local (UTC+8) period in Python rather than
        # relying on SQL date-math dialect differences.
        period = (row.start_time + timedelta(hours=8)).strftime("%Y%m")
        counters[period] = counters.get(period, 0) + 1
        code = f"{period}-{counters[period]:05d}"
        connection.execute(
            sa.text("UPDATE tpc_trips SET trip_code = :code WHERE id = :id"),
            {"code": code, "id": row.id},
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_tpc_trips_trip_code"), table_name="tpc_trips")
    op.drop_column("tpc_trips", "trip_code")
