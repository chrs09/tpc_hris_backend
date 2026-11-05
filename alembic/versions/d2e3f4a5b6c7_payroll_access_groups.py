"""module access: payroll groups a Payroll grant is limited to

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_employee_module_access",
        sa.Column("payroll_groups", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("tpc_employee_module_access", "payroll_groups")
