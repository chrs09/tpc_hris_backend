"""add store is_hub flag and app_settings table

Revision ID: ae3ed60b3564
Revises: 28c593151b9d
Create Date: 2026-09-07 13:20:25.018322

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ae3ed60b3564'
down_revision: Union[str, Sequence[str], None] = '28c593151b9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- tpc_stores.is_hub -------------------------------------------
    # Replaces the hardcoded HUB_NAMES / EXCLUDED_STORE_NAMES sets in
    # app/api/driver/trips.py with a real column on the store record.
    op.add_column(
        "tpc_stores",
        sa.Column(
            "is_hub",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # Backfill: these four rows are exactly what the old hardcoded
    # HUB_NAMES set ({"Yard", "Plant", "Consolacion", "Test Hub"}) matched,
    # so this preserves current behavior with no functional change.
    op.execute(
        """
        UPDATE tpc_stores
        SET is_hub = TRUE
        WHERE name IN ('Yard', 'Plant', 'Consolacion', 'Test Hub')
        """
    )

    # ---- tpc_app_settings ----------------------------------------------
    # Generic key/value table for small settings that used to be plain
    # Python constants. First user: WALLET_SETTLEMENT_SOURCE in
    # app/api/driver/trips.py.
    op.create_table(
        "tpc_app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(
        op.f("ix_tpc_app_settings_key"),
        "tpc_app_settings",
        ["key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_tpc_app_settings_id"),
        "tpc_app_settings",
        ["id"],
        unique=False,
    )

    # Seed with the value that WALLET_SETTLEMENT_SOURCE was hardcoded to,
    # again so this migration is a no-op for current behavior.
    op.execute(
        """
        INSERT INTO tpc_app_settings (`key`, value, description, updated_at)
        VALUES (
            'wallet_settlement_source',
            'coordinator',
            'Which TripFinanceReview date column decides which payroll cutoff a driver''s trip earnings settle into. One of: coordinator, office, finance. See get_wallet_settlement_source() in app/api/driver/trips.py.',
            UTC_TIMESTAMP()
        )
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tpc_app_settings_id"), table_name="tpc_app_settings")
    op.drop_index(op.f("ix_tpc_app_settings_key"), table_name="tpc_app_settings")
    op.drop_table("tpc_app_settings")

    op.drop_column("tpc_stores", "is_hub")
