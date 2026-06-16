"""create vehicle unit model

Revision ID: 00084f9a5efa
Revises: caebfe290689
Create Date: 2026-06-11 17:12:41.863137

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "00084f9a5efa"
down_revision: Union[str, Sequence[str], None] = "caebfe290689"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tpc_vehicle_units",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("unit_code", sa.String(length=50), nullable=True),
        sa.Column("plate_number", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unit_code"),
        sa.UniqueConstraint("plate_number"),
    )

    op.create_index(
        op.f("ix_tpc_vehicle_units_id"),
        "tpc_vehicle_units",
        ["id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_tpc_vehicle_units_plate_number"),
        "tpc_vehicle_units",
        ["plate_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tpc_vehicle_units_plate_number"),
        table_name="tpc_vehicle_units",
    )

    op.drop_index(
        op.f("ix_tpc_vehicle_units_id"),
        table_name="tpc_vehicle_units",
    )

    op.drop_table("tpc_vehicle_units")
