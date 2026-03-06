"""update gps_logs model

Revision ID: 73abfa74a6ab
Revises: 7686a2f4dd76
Create Date: 2026-03-06
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers
revision: str = "73abfa74a6ab"
down_revision: Union[str, Sequence[str], None] = "7686a2f4dd76"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # --------------------------------------
    # Add new columns
    # --------------------------------------
    op.add_column(
        "tpc_gps_logs",
        sa.Column("trip_id", sa.Integer(), nullable=True),
    )

    op.add_column(
        "tpc_gps_logs",
        sa.Column("accuracy", sa.Float(), nullable=True),
    )

    op.add_column(
        "tpc_gps_logs",
        sa.Column("speed", sa.Float(), nullable=True),
    )

    # --------------------------------------
    # Update ENUM to include TRACK
    # --------------------------------------
    op.execute("""
        ALTER TABLE tpc_gps_logs
        MODIFY action_type ENUM('TRACK','CHECK_IN','CHECK_OUT') NOT NULL
        """)

    # --------------------------------------
    # Modify nullable fields
    # --------------------------------------
    op.alter_column(
        "tpc_gps_logs",
        "trip_stop_id",
        existing_type=mysql.INTEGER(),
        nullable=True,
    )

    op.alter_column(
        "tpc_gps_logs",
        "store_lat",
        existing_type=mysql.FLOAT(),
        nullable=True,
    )

    op.alter_column(
        "tpc_gps_logs",
        "store_long",
        existing_type=mysql.FLOAT(),
        nullable=True,
    )

    op.alter_column(
        "tpc_gps_logs",
        "calculated_distance",
        existing_type=mysql.FLOAT(),
        nullable=True,
    )

    op.alter_column(
        "tpc_gps_logs",
        "is_valid",
        existing_type=mysql.TINYINT(display_width=1),
        nullable=True,
    )

    # --------------------------------------
    # Indexes
    # --------------------------------------
    op.create_index(
        "ix_tpc_gps_logs_trip_id",
        "tpc_gps_logs",
        ["trip_id"],
        unique=False,
    )

    op.create_index(
        "ix_tpc_gps_logs_action_type",
        "tpc_gps_logs",
        ["action_type"],
        unique=False,
    )

    op.create_index(
        "ix_tpc_gps_logs_created_at",
        "tpc_gps_logs",
        ["created_at"],
        unique=False,
    )
    op.execute(
        "ALTER TABLE tpc_gps_logs MODIFY action_type ENUM('TRACK','CHECK_IN','CHECK_OUT') NOT NULL"
    )

    # --------------------------------------
    # Foreign key
    # --------------------------------------
    op.create_foreign_key(
        "fk_gps_logs_trip",
        "tpc_gps_logs",
        "tpc_trips",
        ["trip_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint("fk_gps_logs_trip", "tpc_gps_logs", type_="foreignkey")

    op.drop_index("ix_tpc_gps_logs_trip_id", table_name="tpc_gps_logs")
    op.drop_index("ix_tpc_gps_logs_action_type", table_name="tpc_gps_logs")
    op.drop_index("ix_tpc_gps_logs_created_at", table_name="tpc_gps_logs")

    op.alter_column(
        "tpc_gps_logs",
        "is_valid",
        existing_type=mysql.TINYINT(display_width=1),
        nullable=False,
    )

    op.alter_column(
        "tpc_gps_logs",
        "calculated_distance",
        existing_type=mysql.FLOAT(),
        nullable=False,
    )

    op.alter_column(
        "tpc_gps_logs",
        "store_long",
        existing_type=mysql.FLOAT(),
        nullable=False,
    )

    op.alter_column(
        "tpc_gps_logs",
        "store_lat",
        existing_type=mysql.FLOAT(),
        nullable=False,
    )

    op.alter_column(
        "tpc_gps_logs",
        "trip_stop_id",
        existing_type=mysql.INTEGER(),
        nullable=False,
    )

    op.drop_column("tpc_gps_logs", "speed")
    op.drop_column("tpc_gps_logs", "accuracy")
    op.drop_column("tpc_gps_logs", "trip_id")
