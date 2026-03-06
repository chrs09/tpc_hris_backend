"""add trip helper relationship

Revision ID: 93dfa1cb4f66
Revises: e0daa4aab5b1
Create Date: 2026-03-03 10:14:50.899639

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "93dfa1cb4f66"
down_revision: Union[str, Sequence[str], None] = "e0daa4aab5b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_available column
    op.add_column(
        "tpc_employees",
        sa.Column("is_available", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("tpc_employees", "is_available", server_default=None)

    # Create trip helpers table
    op.create_table(
        "tpc_trip_helpers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "trip_id",
            sa.Integer(),
            sa.ForeignKey("tpc_trips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "helper_id",
            sa.Integer(),
            sa.ForeignKey("tpc_employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("tpc_trip_helpers")
    op.drop_column("tpc_employees", "is_available")
    # ### end Alembic commands ###
