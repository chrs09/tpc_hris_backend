"""Module access: view_scope ("all" = see everyone's records, e.g. Expenses)

Revision ID: e1f2a3b4c5d7
Revises: d0e1f2a3b4c6
Create Date: 2026-11-25
"""

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d7"
down_revision = "d0e1f2a3b4c6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_employee_module_access",
        sa.Column("view_scope", sa.String(10), nullable=True),
    )


def downgrade():
    op.drop_column("tpc_employee_module_access", "view_scope")
