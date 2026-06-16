"""add fk for vehicle and trip id

Revision ID: b15d7ae6cb49
Revises: 7b7b49fb49d3
Create Date: 2026-06-15 08:49:19.463206

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b15d7ae6cb49"
down_revision: Union[str, Sequence[str], None] = "7b7b49fb49d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "tpc_trips", sa.Column("vehicle_unit_id", sa.Integer(), nullable=True)
    )

    op.add_column(
        "tpc_trips", sa.Column("trip_category", sa.String(length=50), nullable=True)
    )

    op.create_foreign_key(
        "fk_trip_vehicle_unit",
        "tpc_trips",
        "tpc_vehicle_units",
        ["vehicle_unit_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_trip_vehicle_unit", "tpc_trips", type_="foreignkey")

    op.drop_column("tpc_trips", "trip_category")

    op.drop_column("tpc_trips", "vehicle_unit_id")
