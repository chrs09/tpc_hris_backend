"""trip charges: shortages and accidents, deducted through payroll

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-10-31
"""

import sqlalchemy as sa
from alembic import op

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_trip_charges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("charge_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="recorded"),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("tpc_trips.id"), nullable=False),
        sa.Column("incident_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("shipment_no", sa.String(100), nullable=True),
        sa.Column("report_reference", sa.String(100), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("item", sa.String(255), nullable=True),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=True),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("insurance_status", sa.String(20), nullable=True),
        sa.Column("insurance_reference", sa.String(100), nullable=True),
        sa.Column("participation_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("investigation_result", sa.String(20), nullable=True),
        sa.Column("investigation_notes", sa.Text(), nullable=True),
        sa.Column("chargeable_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("chargeable_reason", sa.Text(), nullable=True),
        sa.Column("attachments", sa.Text(), nullable=True),
        sa.Column("history", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_tpc_trip_charges_id", "tpc_trip_charges", ["id"])
    op.create_index("ix_tpc_trip_charges_charge_type", "tpc_trip_charges", ["charge_type"])
    op.create_index("ix_tpc_trip_charges_status", "tpc_trip_charges", ["status"])
    op.create_index("ix_tpc_trip_charges_trip_id", "tpc_trip_charges", ["trip_id"])

    op.create_table(
        "tpc_trip_charge_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "trip_charge_id",
            sa.Integer(),
            sa.ForeignKey("tpc_trip_charges.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("tpc_employees.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("deduction_per_pay", sa.Numeric(12, 2), nullable=True),
        sa.Column("notified_at", sa.DateTime(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
    )
    op.create_index("ix_tpc_trip_charge_allocations_id", "tpc_trip_charge_allocations", ["id"])
    op.create_index(
        "ix_tpc_trip_charge_allocations_trip_charge_id",
        "tpc_trip_charge_allocations",
        ["trip_charge_id"],
    )
    op.create_index(
        "ix_tpc_trip_charge_allocations_employee_id",
        "tpc_trip_charge_allocations",
        ["employee_id"],
    )

    op.create_table(
        "tpc_trip_charge_deduction_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "allocation_id",
            sa.Integer(),
            sa.ForeignKey("tpc_trip_charge_allocations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payroll_cutoff_period", sa.String(50), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tpc_trip_charge_deduction_logs_id", "tpc_trip_charge_deduction_logs", ["id"])
    op.create_index(
        "ix_tpc_trip_charge_deduction_logs_allocation_id",
        "tpc_trip_charge_deduction_logs",
        ["allocation_id"],
    )
    op.create_index(
        "ix_tpc_trip_charge_deduction_logs_payroll_cutoff_period",
        "tpc_trip_charge_deduction_logs",
        ["payroll_cutoff_period"],
    )

    op.add_column(
        "payroll_deductions",
        sa.Column("trip_charge_deduction", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("payroll_deductions", "trip_charge_deduction")
    op.drop_table("tpc_trip_charge_deduction_logs")
    op.drop_table("tpc_trip_charge_allocations")
    op.drop_table("tpc_trip_charges")
