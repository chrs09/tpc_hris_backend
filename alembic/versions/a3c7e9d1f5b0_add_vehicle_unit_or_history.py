"""add vehicle unit OR history table

Revision ID: a3c7e9d1f5b0
Revises: 17d1bfa74c59
Create Date: 2026-09-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a3c7e9d1f5b0"
down_revision = "17d1bfa74c59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tpc_vehicle_unit_or_history",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "vehicle_unit_id",
            sa.Integer(),
            sa.ForeignKey("tpc_vehicle_units.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("or_number", sa.String(100), nullable=True),
        sa.Column("or_document_url", sa.String(500), nullable=True),
        sa.Column("or_expiration_date", sa.Date(), nullable=True),
        sa.Column("replaced_at", sa.DateTime(), nullable=False),
        sa.Column("replaced_by", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("tpc_vehicle_unit_or_history")
