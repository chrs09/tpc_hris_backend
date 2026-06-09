"""added overtime approval details

Revision ID: 028db704ff06
Revises: 2dc455c31a10
Create Date: 2026-06-04 15:20:32.951684

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "028db704ff06"
down_revision: Union[str, Sequence[str], None] = "2dc455c31a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "tpc_overtime_approval_details",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "overtime_approval_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "attendance_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "detected_ot_hours",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "approved_ot_hours",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.ForeignKeyConstraint(
            ["overtime_approval_id"],
            ["tpc_overtime_approvals.id"],
        ),
        sa.ForeignKeyConstraint(
            ["attendance_id"],
            ["tpc_attendance_records.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_tpc_overtime_approval_details_id"),
        "tpc_overtime_approval_details",
        ["id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_tpc_overtime_approval_details_id"),
        table_name="tpc_overtime_approval_details",
    )

    op.drop_table("tpc_overtime_approval_details")
