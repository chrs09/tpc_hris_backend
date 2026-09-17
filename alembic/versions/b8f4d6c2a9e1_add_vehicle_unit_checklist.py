"""add vehicle unit checklist table

Revision ID: b8f4d6c2a9e1
Revises: a3c7e9d1f5b0
Create Date: 2026-09-17 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b8f4d6c2a9e1"
down_revision = "a3c7e9d1f5b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tpc_vehicle_unit_checklists",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "vehicle_unit_id",
            sa.Integer(),
            sa.ForeignKey("tpc_vehicle_units.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("data", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("tpc_vehicle_unit_checklists")
