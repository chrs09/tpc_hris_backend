"""rename trip_management.trip_bypass module key to trip_assignment

Revision ID: 959efe980feb
Revises: fae0d73f2ee8
Create Date: 2026-09-15 08:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '959efe980feb'
down_revision: Union[str, Sequence[str], None] = 'fae0d73f2ee8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_KEY = "trip_management.trip_bypass"
NEW_KEY = "trip_management.trip_assignment"


def upgrade() -> None:
    """The "Start Trip (Bypass)" page (dispatch) is being renamed to
    "Trip Assignment" -- its module key needs to match, and its old name
    is being reused for the genuinely new "bypass a stuck trip" feature
    (trip_management.trip_bypass_actions), so any existing grant of the
    old key must move to the new one rather than silently vanishing."""
    op.execute(
        sa.text(
            "UPDATE tpc_employee_module_access "
            "SET module_key = :new_key WHERE module_key = :old_key"
        ).bindparams(new_key=NEW_KEY, old_key=OLD_KEY)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE tpc_employee_module_access "
            "SET module_key = :old_key WHERE module_key = :new_key"
        ).bindparams(old_key=OLD_KEY, new_key=NEW_KEY)
    )
