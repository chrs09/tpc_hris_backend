"""employee inactive record: date clearance completed (separation
documents -- resignation letter, clearance, waiver and quitclaim -- are
files on the record: entity_type "employee_separation")

Revision ID: e2b3c4d5f6a7
Revises: d1a2b3c4e5f6
Create Date: 2026-10-14
"""

import sqlalchemy as sa
from alembic import op

revision = "e2b3c4d5f6a7"
down_revision = "d1a2b3c4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_employee_inactive_records",
        sa.Column("clearance_completed_date", sa.Date(), nullable=True),
    )


def downgrade():
    op.drop_column("tpc_employee_inactive_records", "clearance_completed_date")
