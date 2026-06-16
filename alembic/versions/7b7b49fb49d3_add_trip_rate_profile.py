"""add trip rate profile

Revision ID: 7b7b49fb49d3
Revises: 00084f9a5efa
Create Date: 2026-06-12 15:45:37.294999

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7b7b49fb49d3"
down_revision: Union[str, Sequence[str], None] = "00084f9a5efa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tpc_trip_rate_profiles",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "profile_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "helper_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "driver_first_trip_rate",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "driver_next_trip_rate",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "helper_first_trip_rate",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "helper_next_trip_rate",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.Integer(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_name"),
    )

    op.create_index(
        op.f("ix_tpc_trip_rate_profiles_id"),
        "tpc_trip_rate_profiles",
        ["id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_tpc_trip_rate_profiles_profile_name"),
        "tpc_trip_rate_profiles",
        ["profile_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tpc_trip_rate_profiles_profile_name"),
        table_name="tpc_trip_rate_profiles",
    )

    op.drop_index(
        op.f("ix_tpc_trip_rate_profiles_id"),
        table_name="tpc_trip_rate_profiles",
    )

    op.drop_table("tpc_trip_rate_profiles")
