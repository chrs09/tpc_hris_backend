"""trip expenses: driver trip budgets (release + liquidation) and expense reports

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-11-06
"""

import sqlalchemy as sa
from alembic import op

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_trip_expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("tpc_employees.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("filed_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("tpc_trips.id"), nullable=True),
        sa.Column("vehicle_unit_id", sa.Integer(), sa.ForeignKey("tpc_vehicle_units.id"), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("approval_chain", sa.Text(), nullable=True),
        sa.Column("approval_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approval_log", sa.Text(), nullable=True),
        sa.Column("released_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("release_method", sa.String(10), nullable=True),
        sa.Column("release_reference", sa.String(100), nullable=True),
        sa.Column("release_photo_url", sa.String(1000), nullable=True),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("released_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("allowed_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("short_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("short_settlement", sa.String(20), nullable=True),
        sa.Column("trip_charge_id", sa.Integer(), sa.ForeignKey("tpc_trip_charges.id"), nullable=True),
        sa.Column("reimburse_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("reimburse_payroll_date", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("history", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    for col in ("kind", "status", "employee_id", "user_id", "trip_id", "reimburse_payroll_date"):
        op.create_index(f"ix_tpc_trip_expenses_{col}", "tpc_trip_expenses", [col])
    op.create_index("ix_tpc_trip_expenses_id", "tpc_trip_expenses", ["id"])

    op.create_table(
        "tpc_trip_expense_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "expense_id",
            sa.Integer(),
            sa.ForeignKey("tpc_trip_expenses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(10), nullable=False, server_default="actual"),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("expense_date", sa.Date(), nullable=True),
        sa.Column("receipt_url", sa.String(1000), nullable=True),
        sa.Column("allowed_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("review_note", sa.String(500), nullable=True),
    )
    op.create_index("ix_tpc_trip_expense_lines_id", "tpc_trip_expense_lines", ["id"])
    op.create_index("ix_tpc_trip_expense_lines_expense_id", "tpc_trip_expense_lines", ["expense_id"])


def downgrade():
    op.drop_table("tpc_trip_expense_lines")
    op.drop_table("tpc_trip_expenses")
