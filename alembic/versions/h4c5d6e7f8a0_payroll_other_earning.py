"""Payroll: Others (earning) amount and what it's for

Revision ID: h4c5d6e7f8a0
Revises: g3b4c5d6e7f9
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "h4c5d6e7f8a0"
down_revision = "g3b4c5d6e7f9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payroll_deductions", sa.Column("other_earning", sa.Numeric(12, 2), nullable=True))
    op.add_column("payroll_deductions", sa.Column("other_earning_note", sa.String(200), nullable=True))


def downgrade():
    op.drop_column("payroll_deductions", "other_earning_note")
    op.drop_column("payroll_deductions", "other_earning")
