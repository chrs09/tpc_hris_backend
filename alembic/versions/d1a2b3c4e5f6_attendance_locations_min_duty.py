"""attendance locations (editable perimeters), assigned locations and
minimum hours of duty per employee, short-duty flag on attendance

Revision ID: d1a2b3c4e5f6
Revises: c9e1a3b5d748
Create Date: 2026-10-13
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "d1a2b3c4e5f6"
down_revision = "c9e1a3b5d748"
branch_labels = None
depends_on = None

# The locations that were hardcoded in app/api/attendance.py -- same
# behavior right after the upgrade.
SEED = [
    ("TPC Yard", 10.345240, 123.936819, 150),
    ("Test Location", 10.359618, 123.973413, 150),
    ("Consolacion Office", 10.3787, 123.9666, 150),
    ("Mandaue Plant", 10.3305, 123.9333, 350),
    ("Cordova", 10.2545, 123.9487, 150),
]


def upgrade():
    locations = op.create_table(
        "tpc_attendance_locations",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("radius_meters", sa.Integer(), nullable=False, server_default="150"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    now = datetime.utcnow()
    op.bulk_insert(
        locations,
        [
            {
                "name": name,
                "latitude": lat,
                "longitude": lng,
                "radius_meters": radius,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for name, lat, lng, radius in SEED
        ],
    )

    # JSON list of tpc_attendance_locations ids; NULL/empty = any active.
    op.add_column("tpc_employees", sa.Column("attendance_location_ids", sa.Text(), nullable=True))
    # Minutes between time in and time out before it counts as a day of
    # duty; NULL = the company default (app setting below).
    op.add_column("tpc_employees", sa.Column("min_duty_minutes", sa.Integer(), nullable=True))

    op.add_column(
        "tpc_attendance_records",
        sa.Column("short_duty", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    settings = sa.table(
        "tpc_app_settings",
        sa.column("key", sa.String),
        sa.column("value", sa.String),
        sa.column("description", sa.Text),
        sa.column("updated_at", sa.DateTime),
    )
    op.bulk_insert(
        settings,
        [
            {
                "key": "attendance_min_duty_minutes",
                "value": "240",
                "description": (
                    "Minimum minutes between time in and time out. Shorter = "
                    "Short duty: counted Absent until the attendance approvers "
                    "approve it. 0 = off. Employees can have their own."
                ),
                "updated_at": now,
            }
        ],
    )


def downgrade():
    op.execute("DELETE FROM tpc_app_settings WHERE `key` = 'attendance_min_duty_minutes'")
    op.drop_column("tpc_attendance_records", "short_duty")
    op.drop_column("tpc_employees", "min_duty_minutes")
    op.drop_column("tpc_employees", "attendance_location_ids")
    op.drop_table("tpc_attendance_locations")
