"""add dispatched_by_user_id to trips

Revision ID: 46199763822b
Revises: a1c3f9d2b6e4
Create Date: 2026-09-24 13:26:40.139214

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46199763822b'
down_revision: Union[str, Sequence[str], None] = 'a1c3f9d2b6e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tpc_trips",
        sa.Column("dispatched_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_tpc_trips_dispatched_by_user_id",
        "tpc_trips",
        "tpc_users",
        ["dispatched_by_user_id"],
        ["id"],
    )

    # created_at previously used MySQL's own NOW() as a server-side
    # default, which reflects this DB server's local clock (PH time)
    # instead of UTC, double-offsetting every displayed dispatch time
    # once utc_to_ph() added another +8 on top. The ORM model now sets
    # it in Python via datetime.utcnow() instead, so drop the
    # conflicting server default to match.
    op.alter_column(
        "tpc_trips",
        "created_at",
        existing_type=sa.DateTime(),
        server_default=None,
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "fk_tpc_trips_dispatched_by_user_id", "tpc_trips", type_="foreignkey"
    )
    op.drop_column("tpc_trips", "dispatched_by_user_id")
