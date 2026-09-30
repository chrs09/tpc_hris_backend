"""attendance adjustments

Audit trail for attendance edited by hand: old value, new value, who,
when and why.

Revision ID: f8b4d2e6a931
Revises: e3a6c8d1f245
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa


revision = "f8b4d2e6a931"
down_revision = "e3a6c8d1f245"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_attendance_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "attendance_id",
            sa.Integer(),
            sa.ForeignKey("tpc_attendance_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field", sa.String(30), nullable=False),
        sa.Column("old_value", sa.String(255), nullable=True),
        sa.Column("new_value", sa.String(255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "changed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("tpc_users.id"),
            nullable=True,
        ),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_tpc_attendance_adjustments_attendance_id",
        "tpc_attendance_adjustments",
        ["attendance_id"],
    )


def downgrade():
    op.drop_index(
        "ix_tpc_attendance_adjustments_attendance_id",
        table_name="tpc_attendance_adjustments",
    )
    op.drop_table("tpc_attendance_adjustments")
