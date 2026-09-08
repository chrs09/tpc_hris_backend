"""add overtime request tables

Revision ID: e6b34f893133
Revises: e4b016e4d0d9
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6b34f893133'
down_revision: Union[str, Sequence[str], None] = 'e4b016e4d0d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Roster of users selectable as the approver on an overtime request.
    # See app/models/overtime_approver.py.
    op.create_table(
        "tpc_overtime_approvers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("added_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["tpc_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["added_by_user_id"], ["tpc_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_tpc_overtime_approvers_id"),
        "tpc_overtime_approvers",
        ["id"],
        unique=False,
    )

    # Employee-initiated callback overtime requests. See
    # app/models/overtime_request.py.
    op.create_table(
        "tpc_overtime_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("ot_date", sa.Date(), nullable=False),
        sa.Column("time_in", sa.Time(), nullable=False),
        sa.Column("time_out", sa.Time(), nullable=False),
        sa.Column("computed_hours", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("approved_hours", sa.Float(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("overtime_approval_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["tpc_users.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["tpc_employees.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["tpc_users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["tpc_users.id"]),
        sa.ForeignKeyConstraint(
            ["overtime_approval_id"], ["tpc_overtime_approvals.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tpc_overtime_requests_id"),
        "tpc_overtime_requests",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tpc_overtime_requests_id"), table_name="tpc_overtime_requests")
    op.drop_table("tpc_overtime_requests")
    op.drop_index(op.f("ix_tpc_overtime_approvers_id"), table_name="tpc_overtime_approvers")
    op.drop_table("tpc_overtime_approvers")
