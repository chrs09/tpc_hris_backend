"""add trip archive flags

Revision ID: d92e6a3f18c4
Revises: c8f4a17e2b90
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd92e6a3f18c4'
down_revision: Union[str, Sequence[str], None] = 'c8f4a17e2b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_trips",
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("tpc_trips", "is_archived", server_default=None)

    op.add_column(
        "tpc_trips", sa.Column("archived_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "tpc_trips",
        sa.Column("archived_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_tpc_trips_archived_by_user_id",
        "tpc_trips",
        "tpc_users",
        ["archived_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_tpc_trips_archived_by_user_id", "tpc_trips", type_="foreignkey"
    )
    op.drop_column("tpc_trips", "archived_by_user_id")
    op.drop_column("tpc_trips", "archived_at")
    op.drop_column("tpc_trips", "is_archived")
