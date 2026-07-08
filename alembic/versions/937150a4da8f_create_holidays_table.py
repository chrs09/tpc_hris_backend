"""create holidays table

Revision ID: 937150a4da8f
Revises: 3c761990366d
Create Date: 2026-07-08 14:35:51.009976

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '937150a4da8f'
down_revision: Union[str, Sequence[str], None] = '3c761990366d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tpc_holidays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("holiday_name", sa.String(255), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("holiday_type", sa.String(50), nullable=False),
        sa.Column("scope", sa.String(50), nullable=False),
        sa.Column("province", sa.String(100), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("override_api", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_index(
        "ix_tpc_holidays_holiday_date",
        "tpc_holidays",
        ["holiday_date"],
    )

    op.create_index(
        "ix_tpc_holidays_id",
        "tpc_holidays",
        ["id"],
    )

def downgrade() -> None:
    op.drop_index(
        "ix_tpc_holidays_id",
        table_name="tpc_holidays",
    )

    op.drop_index(
        "ix_tpc_holidays_holiday_date",
        table_name="tpc_holidays",
    )

    op.drop_table("tpc_holidays")