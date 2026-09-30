"""overtime late filing

"File missed overtime" and "forgot to clock out" support: flags for a
request filed after the fact or with a typed-in time out, plus the
employee's explanation.

Revision ID: c5e8a1f3d207
Revises: b41d7e2a9c63
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa


revision = "c5e8a1f3d207"
down_revision = "b41d7e2a9c63"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_overtime_requests",
        sa.Column("filed_late", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tpc_overtime_requests",
        sa.Column("manual_time_out", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column("tpc_overtime_requests", sa.Column("late_note", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("tpc_overtime_requests", "late_note")
    op.drop_column("tpc_overtime_requests", "manual_time_out")
    op.drop_column("tpc_overtime_requests", "filed_late")
