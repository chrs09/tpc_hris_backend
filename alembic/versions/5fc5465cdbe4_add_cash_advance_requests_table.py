"""add cash advance requests table

Revision ID: 5fc5465cdbe4
Revises: 0251470ba847
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5fc5465cdbe4'
down_revision: Union[str, Sequence[str], None] = '0251470ba847'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Employee-initiated cash advance requests, approved by the filer's
    # department head. See app/models/cash_advance_request.py.
    op.create_table(
        "tpc_cash_advance_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["tpc_users.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["tpc_employees.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["tpc_users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["tpc_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tpc_cash_advance_requests_id"),
        "tpc_cash_advance_requests",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tpc_cash_advance_requests_id"),
        table_name="tpc_cash_advance_requests",
    )
    op.drop_table("tpc_cash_advance_requests")
