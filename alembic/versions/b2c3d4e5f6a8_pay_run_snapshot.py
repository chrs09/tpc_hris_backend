"""pay run snapshot + pre-check on payroll runs

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "b2c3d4e5f6a8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_payroll_runs",
        sa.Column("snapshot", sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql"), nullable=True),
    )
    op.add_column("tpc_payroll_runs", sa.Column("snapshot_at", sa.DateTime(), nullable=True))
    op.add_column("tpc_payroll_runs", sa.Column("snapshot_by", sa.Integer(), nullable=True))
    op.add_column("tpc_payroll_runs", sa.Column("precheck", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("tpc_payroll_runs", "precheck")
    op.drop_column("tpc_payroll_runs", "snapshot_by")
    op.drop_column("tpc_payroll_runs", "snapshot_at")
    op.drop_column("tpc_payroll_runs", "snapshot")
