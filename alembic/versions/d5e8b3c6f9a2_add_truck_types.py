"""add truck types table and vehicle_units.truck_type_id

Revision ID: d5e8b3c6f9a2
Revises: c1d9f3a7b2e4
Create Date: 2026-09-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d5e8b3c6f9a2"
down_revision = "c1d9f3a7b2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tpc_truck_types",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("size", sa.String(100), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.add_column(
        "tpc_vehicle_units",
        sa.Column(
            "truck_type_id",
            sa.Integer(),
            sa.ForeignKey("tpc_truck_types.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("tpc_vehicle_units", "truck_type_id")
    op.drop_table("tpc_truck_types")
