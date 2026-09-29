"""org chart approval chains

Org chart heads can approve Cash Advance / Overtime / Attendance for the
units under them, layer by layer. Adds what each head approves and the
per-request chain/step/log.

Revision ID: b41d7e2a9c63
Revises: 7a3c91d2e4b5
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa


revision = "b41d7e2a9c63"
down_revision = "7a3c91d2e4b5"
branch_labels = None
depends_on = None


def _chain_columns(table, prefix):
    op.add_column(table, sa.Column(f"{prefix}_chain", sa.Text(), nullable=True))
    op.add_column(
        table,
        sa.Column(f"{prefix}_step", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(table, sa.Column(f"{prefix}_log", sa.Text(), nullable=True))


def _drop_chain_columns(table, prefix):
    for suffix in ("log", "step", "chain"):
        op.drop_column(table, f"{prefix}_{suffix}")


def upgrade():
    op.add_column("tpc_org_units", sa.Column("approves", sa.Text(), nullable=True))
    _chain_columns("tpc_cash_advance_requests", "approval")
    _chain_columns("tpc_overtime_requests", "approval")
    _chain_columns("tpc_attendance_records", "time_in_review")
    _chain_columns("tpc_attendance_records", "time_out_review")


def downgrade():
    _drop_chain_columns("tpc_attendance_records", "time_out_review")
    _drop_chain_columns("tpc_attendance_records", "time_in_review")
    _drop_chain_columns("tpc_overtime_requests", "approval")
    _drop_chain_columns("tpc_cash_advance_requests", "approval")
    op.drop_column("tpc_org_units", "approves")
