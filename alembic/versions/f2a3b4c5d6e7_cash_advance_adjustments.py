"""cash advance: adjustment entries (correct the amount actually released)

An adjustment is a log entry next to deductions, so the balance is still
approved amount minus all entries, but it isn't money taken from pay.
Existing entries are all deductions.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-10-31
"""

import sqlalchemy as sa
from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_cash_advance_deduction_logs",
        sa.Column("entry_type", sa.String(20), nullable=False, server_default="deduction"),
    )


def downgrade():
    # Removing an adjustment's row would change the balance, so a downgrade
    # keeps those rows; they count as plain entries in the old balance math.
    op.drop_column("tpc_cash_advance_deduction_logs", "entry_type")
