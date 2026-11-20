"""pay date on payroll runs

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b9"
down_revision = "b2c3d4e5f6a8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_payroll_runs", sa.Column("pay_date", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("tpc_payroll_runs", "pay_date")
