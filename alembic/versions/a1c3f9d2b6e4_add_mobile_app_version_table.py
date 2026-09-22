"""add mobile app version table

Revision ID: a1c3f9d2b6e4
Revises: b8d4f1a6c9e7
Create Date: 2026-09-22 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c3f9d2b6e4"
down_revision: Union[str, Sequence[str], None] = "b8d4f1a6c9e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tpc_mobile_app_versions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("platform", sa.String(length=20), nullable=False, unique=True, index=True),
        sa.Column("latest_version", sa.String(length=20), nullable=False),
        sa.Column("min_supported_version", sa.String(length=20), nullable=False),
        sa.Column("apk_url", sa.Text(), nullable=False),
        sa.Column("release_notes", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["tpc_users.id"]),
    )


def downgrade() -> None:
    op.drop_table("tpc_mobile_app_versions")
