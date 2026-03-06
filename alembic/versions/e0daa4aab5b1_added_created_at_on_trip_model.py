"""added created_at on trip model

Revision ID: e0daa4aab5b1
Revises: 4cb5982e02c4
Create Date: 2026-03-02 16:30:30.137933

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e0daa4aab5b1"
down_revision: Union[str, Sequence[str], None] = "4cb5982e02c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # 1️⃣ Backfill existing NULL rows
    op.execute("UPDATE tpc_trips SET created_at = NOW() WHERE created_at IS NULL")

    # 2️⃣ Alter column to add default
    op.alter_column(
        "tpc_trips",
        "created_at",
        existing_type=sa.DateTime(),
        server_default=sa.func.now(),
        nullable=False,
    )


def downgrade():
    op.alter_column(
        "tpc_trips",
        "created_at",
        existing_type=sa.DateTime(),
        server_default=None,
        nullable=True,
    )
