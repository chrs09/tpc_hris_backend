"""added dispatch helper

Revision ID: 921187fa9cf8
Revises: 4199b6057a9d
Create Date: 2026-07-09 14:43:55.166872

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '921187fa9cf8'
down_revision: Union[str, Sequence[str], None] = '4199b6057a9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.create_table(
        "tpc_dispatch_helpers",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),

        sa.Column(
            "dispatch_item_id",
            sa.Integer(),
            sa.ForeignKey(
                "tpc_dispatch_items.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),

        sa.Column(
            "helper_id",
            sa.Integer(),
            sa.ForeignKey(
                "tpc_employees.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_tpc_dispatch_helpers_dispatch_item",
        "tpc_dispatch_helpers",
        ["dispatch_item_id"],
    )

    op.create_index(
        "ix_tpc_dispatch_helpers_helper",
        "tpc_dispatch_helpers",
        ["helper_id"],
    )


def downgrade() -> None:

    op.drop_index(
        "ix_tpc_dispatch_helpers_helper",
        table_name="tpc_dispatch_helpers",
    )

    op.drop_index(
        "ix_tpc_dispatch_helpers_dispatch_item",
        table_name="tpc_dispatch_helpers",
    )

    op.drop_table(
        "tpc_dispatch_helpers",
    )