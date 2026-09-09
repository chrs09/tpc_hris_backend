"""add employee module access table

Revision ID: 27f1cf9da89f
Revises: d285bdb09102
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '27f1cf9da89f'
down_revision: Union[str, Sequence[str], None] = 'd285bdb09102'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Per-employee submodule grants for the Module Assignment page. See
    # app/models/employee_module_access.py.
    op.create_table(
        "tpc_employee_module_access",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("module_key", sa.String(length=80), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["tpc_employees.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["tpc_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "employee_id", "module_key", name="uq_employee_module"
        ),
    )
    op.create_index(
        op.f("ix_tpc_employee_module_access_id"),
        "tpc_employee_module_access",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tpc_employee_module_access_id"),
        table_name="tpc_employee_module_access",
    )
    op.drop_table("tpc_employee_module_access")
