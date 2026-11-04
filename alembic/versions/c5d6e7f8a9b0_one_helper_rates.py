"""trip rates: helper rates for a 2-helper category when only 1 helper goes

Blank (NULL) on a category = the helper is paid the normal helper rates, so
nothing changes until they're filled. On rate rules, blank keeps the
category's, like every other rate.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None

COLUMNS = (
    "one_helper_first_trip_rate",
    "one_helper_first_other",
    "one_helper_next_trip_rate",
    "one_helper_next_other",
)


def upgrade():
    for name in COLUMNS:
        op.add_column("tpc_trip_rate_profiles", sa.Column(name, sa.Numeric(10, 2), nullable=True))
        op.add_column("tpc_trip_rate_rules", sa.Column(name, sa.Numeric(10, 2), nullable=True))


def downgrade():
    for name in COLUMNS:
        op.drop_column("tpc_trip_rate_rules", name)
        op.drop_column("tpc_trip_rate_profiles", name)
