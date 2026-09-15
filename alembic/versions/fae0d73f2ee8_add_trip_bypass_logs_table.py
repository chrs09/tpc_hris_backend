"""add trip bypass logs table

Revision ID: fae0d73f2ee8
Revises: 00de30e36f68
Create Date: 2026-09-15 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fae0d73f2ee8'
down_revision: Union[str, Sequence[str], None] = '00de30e36f68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tpc_trip_bypass_logs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "trip_id",
            sa.Integer(),
            sa.ForeignKey("tpc_trips.id"),
            nullable=False,
        ),
        sa.Column(
            "stop_id",
            sa.Integer(),
            sa.ForeignKey("tpc_trip_stops.id"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column(
            "performed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("tpc_users.id"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_tpc_trip_bypass_logs_created_at",
        "tpc_trip_bypass_logs",
        ["created_at"],
    )
    op.create_index(
        "ix_tpc_trip_bypass_logs_trip_id",
        "tpc_trip_bypass_logs",
        ["trip_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tpc_trip_bypass_logs_trip_id", table_name="tpc_trip_bypass_logs"
    )
    op.drop_index(
        "ix_tpc_trip_bypass_logs_created_at", table_name="tpc_trip_bypass_logs"
    )
    op.drop_table("tpc_trip_bypass_logs")
