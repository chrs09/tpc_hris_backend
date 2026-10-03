"""trip rate rules, store area, payroll runs

- tpc_trip_rate_rules: driver/helper rates by category / truck type /
  lane (origin -> destination area), with an effective date.
- tpc_stores.area: the area a store is in (e.g. Consolacion, Bohol),
  used as a lane's destination.
- tpc_payroll_runs: payroll status per department + cutoff
  (Draft -> Generated -> For Review -> Approved -> Locked -> Paid).

Revision ID: e5a7c9b1d346
Revises: d2e4f6a8b913
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "e5a7c9b1d346"
down_revision = "d2e4f6a8b913"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_stores", sa.Column("area", sa.String(100), nullable=True))
    op.create_index("ix_tpc_stores_area", "tpc_stores", ["area"])

    op.create_table(
        "tpc_trip_rate_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "trip_rate_profile_id",
            sa.Integer(),
            sa.ForeignKey("tpc_trip_rate_profiles.id"),
            nullable=True,
        ),
        sa.Column(
            "truck_type_id", sa.Integer(), sa.ForeignKey("tpc_truck_types.id"), nullable=True
        ),
        sa.Column(
            "origin_store_id", sa.Integer(), sa.ForeignKey("tpc_stores.id"), nullable=True
        ),
        sa.Column("destination_area", sa.String(100), nullable=True),
        sa.Column("driver_first_trip_rate", sa.Numeric(10, 2), nullable=True),
        sa.Column("driver_next_trip_rate", sa.Numeric(10, 2), nullable=True),
        sa.Column("helper_first_trip_rate", sa.Numeric(10, 2), nullable=True),
        sa.Column("helper_next_trip_rate", sa.Numeric(10, 2), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    for col in ("trip_rate_profile_id", "truck_type_id", "origin_store_id", "destination_area", "effective_from"):
        op.create_index(f"ix_tpc_trip_rate_rules_{col}", "tpc_trip_rate_rules", [col])

    op.create_table(
        "tpc_payroll_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("department", sa.String(50), nullable=False),
        sa.Column("cutoff_period", sa.String(50), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("employee_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_gross", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_net", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("generated_by", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("locked_by", sa.Integer(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("paid_by", sa.Integer(), nullable=True),
        sa.Column("return_note", sa.String(500), nullable=True),
        sa.Column("log", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("department", "cutoff_period", name="uq_payroll_run_dept_cutoff"),
    )
    for col in ("department", "cutoff_period", "period_start", "period_end"):
        op.create_index(f"ix_tpc_payroll_runs_{col}", "tpc_payroll_runs", [col])


def downgrade():
    op.drop_table("tpc_payroll_runs")
    op.drop_table("tpc_trip_rate_rules")
    op.drop_index("ix_tpc_stores_area", table_name="tpc_stores")
    op.drop_column("tpc_stores", "area")
