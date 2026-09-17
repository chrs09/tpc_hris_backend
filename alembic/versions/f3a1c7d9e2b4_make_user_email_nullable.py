"""make tpc_users.email nullable

Revision ID: f3a1c7d9e2b4
Revises: d5e8b3c6f9a2
Create Date: 2026-09-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f3a1c7d9e2b4"
down_revision = "d5e8b3c6f9a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "tpc_users",
        "email",
        existing_type=sa.String(100),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "tpc_users",
        "email",
        existing_type=sa.String(100),
        nullable=False,
    )
