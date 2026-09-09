"""cash advance balance redesign

Revision ID: f21756c7a466
Revises: b97db395ff8f
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f21756c7a466'
down_revision: Union[str, Sequence[str], None] = 'b97db395ff8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `amount` is now typed freely by the driver (total requested); the
    # superadmin preset only sets the per-pay deduction amount, copied
    # here at filing time. installment_months is replaced by a real
    # ledger (tpc_cash_advance_deduction_logs) so "remaining balance" is
    # a real, auditable number instead of a static split.
    op.add_column(
        "tpc_cash_advance_requests",
        sa.Column(
            "deduction_per_pay_amount",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.drop_column("tpc_cash_advance_requests", "installment_months")

    op.create_table(
        "tpc_cash_advance_deduction_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cash_advance_request_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cash_advance_request_id"], ["tpc_cash_advance_requests.id"]
        ),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["tpc_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tpc_cash_advance_deduction_logs_id"),
        "tpc_cash_advance_deduction_logs",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tpc_cash_advance_deduction_logs_id"),
        table_name="tpc_cash_advance_deduction_logs",
    )
    op.drop_table("tpc_cash_advance_deduction_logs")

    op.add_column(
        "tpc_cash_advance_requests",
        sa.Column(
            "installment_months",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.drop_column("tpc_cash_advance_requests", "deduction_per_pay_amount")
