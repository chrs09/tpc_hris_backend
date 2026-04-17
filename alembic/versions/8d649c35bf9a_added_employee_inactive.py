"""added employee inactive

Revision ID: 8d649c35bf9a
Revises: af6729ea13ae
Create Date: 2026-04-16 14:20:38.486277

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "8d649c35bf9a"
down_revision: Union[str, Sequence[str], None] = "af6729ea13ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tpc_employee_inactive_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("inactive_reason", sa.String(length=100), nullable=False),
        sa.Column("inactive_date", sa.Date(), nullable=False),
        sa.Column("inactive_remarks", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reactivated_at", sa.DateTime(), nullable=True),
        sa.Column("reactivated_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["tpc_employees.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["tpc_users.id"]),
        sa.ForeignKeyConstraint(["reactivated_by_user_id"], ["tpc_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tpc_employee_inactive_records_id"),
        "tpc_employee_inactive_records",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tpc_employee_inactive_records_employee_id"),
        "tpc_employee_inactive_records",
        ["employee_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tpc_employee_inactive_records_employee_id"),
        table_name="tpc_employee_inactive_records",
    )
    op.drop_index(
        op.f("ix_tpc_employee_inactive_records_id"),
        table_name="tpc_employee_inactive_records",
    )
    op.drop_table("tpc_employee_inactive_records")
    # ### end Alembic commands ###
