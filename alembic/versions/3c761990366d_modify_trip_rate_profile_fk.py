"""modify trip rate profile fk

Revision ID: 3c761990366d
Revises: df532f429f96
Create Date: 2026-06-15 09:34:40.335862

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "3c761990366d"
down_revision: Union[str, Sequence[str], None] = "df532f429f96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():

    op.add_column(
        "tpc_trips",
        sa.Column(
            "trip_rate_profile_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_trip_rate_profile",
        "tpc_trips",
        "tpc_trip_rate_profiles",
        ["trip_rate_profile_id"],
        ["id"],
    )


def downgrade():

    op.drop_constraint(
        "fk_trip_rate_profile",
        "tpc_trips",
        type_="foreignkey",
    )

    op.drop_column(
        "tpc_trips",
        "trip_rate_profile_id",
    )
