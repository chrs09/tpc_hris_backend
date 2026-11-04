"""trip rates: driver rates for a 2-helper category when only 1 helper goes

With c5d6e7f8a9b0's 1-helper helper rates, these make the 1-helper set the
whole pay of that trip (driver and helper). Blank (NULL) on a category =
the normal driver rates are paid; on rate rules, blank keeps the
category's.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None

COLUMNS = (
    "one_helper_driver_first_trip_rate",
    "one_helper_driver_allowance",
    "one_helper_driver_other",
    "one_helper_driver_next_trip_rate",
    "one_helper_driver_next_other",
)


def upgrade():
    for name in COLUMNS:
        op.add_column("tpc_trip_rate_profiles", sa.Column(name, sa.Numeric(10, 2), nullable=True))
        op.add_column("tpc_trip_rate_rules", sa.Column(name, sa.Numeric(10, 2), nullable=True))


def downgrade():
    for name in COLUMNS:
        op.drop_column("tpc_trip_rate_rules", name)
        op.drop_column("tpc_trip_rate_profiles", name)
