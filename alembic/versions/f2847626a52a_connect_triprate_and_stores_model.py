"""connect triprate and stores model

Revision ID: f2847626a52a
Revises: f76d8c534f57
Create Date: 2026-07-18 13:52:07.467437

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2847626a52a'
down_revision: Union[str, Sequence[str], None] = 'f76d8c534f57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # TripRateProfile.code
    op.add_column(
        "tpc_trip_rate_profiles",
        sa.Column("code", sa.String(length=20), nullable=True),
    )
    op.create_unique_constraint(
        "uq_tpc_trip_rate_profiles_code",
        "tpc_trip_rate_profiles",
        ["code"],
    )
 
    # Store.trip_rate_profile_id
    op.add_column(
        "tpc_stores",
        sa.Column("trip_rate_profile_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_tpc_stores_trip_rate_profile_id",
        "tpc_stores",
        "tpc_trip_rate_profiles",
        ["trip_rate_profile_id"],
        ["id"],
    )
 
    # Store.profile becomes optional going forward (was NOT NULL before)
    op.alter_column(
        "tpc_stores",
        "profile",
        existing_type=sa.String(length=50),
        nullable=True,
    )
 
 
def downgrade():
    op.alter_column(
        "tpc_stores",
        "profile",
        existing_type=sa.String(length=50),
        nullable=False,
    )
 
    op.drop_constraint(
        "fk_tpc_stores_trip_rate_profile_id", "tpc_stores", type_="foreignkey"
    )
    op.drop_column("tpc_stores", "trip_rate_profile_id")
 
    op.drop_constraint(
        "uq_tpc_trip_rate_profiles_code",
        "tpc_trip_rate_profiles",
        type_="unique",
    )
    op.drop_column("tpc_trip_rate_profiles", "code")
