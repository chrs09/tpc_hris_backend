"""unloading GPS saved on each stop; store coordinates updated from it
(safe auto-update) with a location change history

Revision ID: c6f7a8b9d0e1
Revises: b5e6f7a8c9d0
Create Date: 2026-10-19
"""

import sqlalchemy as sa
from alembic import op

revision = "c6f7a8b9d0e1"
down_revision = "b5e6f7a8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_trip_stops", sa.Column("lat_unload", sa.Float(), nullable=True))
    op.add_column("tpc_trip_stops", sa.Column("long_unload", sa.Float(), nullable=True))
    op.add_column("tpc_trip_stops", sa.Column("unload_accuracy_m", sa.Float(), nullable=True))
    op.add_column("tpc_trip_stops", sa.Column("unload_at", sa.DateTime(), nullable=True))

    op.create_table(
        "tpc_store_location_changes",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "store_id",
            sa.Integer(),
            sa.ForeignKey("tpc_stores.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("old_latitude", sa.Float(), nullable=True),
        sa.Column("old_longitude", sa.Float(), nullable=True),
        sa.Column("new_latitude", sa.Float(), nullable=False),
        sa.Column("new_longitude", sa.Float(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=True),
        sa.Column("driver_count", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("tpc_store_location_changes")
    op.drop_column("tpc_trip_stops", "unload_at")
    op.drop_column("tpc_trip_stops", "unload_accuracy_m")
    op.drop_column("tpc_trip_stops", "long_unload")
    op.drop_column("tpc_trip_stops", "lat_unload")
