"""add user_id to leave requests, make employee_id nullable

Revision ID: 28c593151b9d
Revises: 79cb34d9b04d
Create Date: 2026-09-07 11:46:56.344887

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28c593151b9d'
down_revision: Union[str, Sequence[str], None] = '79cb34d9b04d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_leave_requests",
        sa.Column("user_id", sa.Integer(), nullable=False),
    )
    op.create_foreign_key(
        "fk_tpc_leave_requests_user_id",
        "tpc_leave_requests",
        "tpc_users",
        ["user_id"],
        ["id"],
    )
    op.alter_column(
        "tpc_leave_requests",
        "employee_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "tpc_leave_requests",
        "employee_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_constraint(
        "fk_tpc_leave_requests_user_id",
        "tpc_leave_requests",
        type_="foreignkey",
    )
    op.drop_column("tpc_leave_requests", "user_id")
