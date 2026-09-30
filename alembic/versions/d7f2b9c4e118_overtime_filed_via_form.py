"""overtime filed via form

Marks overtime filed through the File Overtime form (vs. the old clock
in/out), so only those can show as "Filed in advance".

Revision ID: d7f2b9c4e118
Revises: c5e8a1f3d207
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa


revision = "d7f2b9c4e118"
down_revision = "c5e8a1f3d207"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_overtime_requests",
        sa.Column("filed_via_form", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("tpc_overtime_requests", "filed_via_form")
