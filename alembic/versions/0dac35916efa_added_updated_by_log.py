"""added updated by log

Revision ID: 0dac35916efa
Revises: 4ea73a071f3b
Create Date: 2026-04-13 10:44:12.919526

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0dac35916efa"
down_revision: Union[str, Sequence[str], None] = "4ea73a071f3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_employees",
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tpc_employees",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_foreign_key(
        "fk_tpc_employees_updated_by_user_id",
        "tpc_employees",
        "tpc_users",
        ["updated_by_user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_tpc_employees_updated_by_user_id",
        "tpc_employees",
        type_="foreignkey",
    )
    op.drop_column("tpc_employees", "updated_at")
    op.drop_column("tpc_employees", "updated_by_user_id")
