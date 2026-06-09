"""added overtime_approval table

Revision ID: 23c73cfe9021
Revises: f74c4886156f
Create Date: 2026-05-30 16:09:38.304305

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "23c73cfe9021"
down_revision: Union[str, Sequence[str], None] = "f74c4886156f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "tpc_overtime_approvals",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),
        sa.Column(
            "employee_id",
            sa.Integer(),
            sa.ForeignKey("tpc_employees.id"),
            nullable=False,
        ),
        sa.Column(
            "cutoff_start",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "cutoff_end",
            sa.Date(),
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
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="Pending",
        ),
        sa.Column(
            "remarks",
            sa.String(500),
            nullable=True,
        ),
        sa.Column(
            "approved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("tpc_users.id"),
            nullable=True,
        ),
        sa.Column(
            "approved_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.Column(
            "reversed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("tpc_users.id"),
            nullable=True,
        ),
        sa.Column(
            "reversed_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_overtime_employee",
        "tpc_overtime_approvals",
        ["employee_id"],
    )

    op.create_index(
        "ix_overtime_cutoff",
        "tpc_overtime_approvals",
        [
            "cutoff_start",
            "cutoff_end",
        ],
    )


def downgrade():
    op.drop_index(
        "ix_overtime_cutoff",
        table_name="tpc_overtime_approvals",
    )

    op.drop_index(
        "ix_overtime_employee",
        table_name="tpc_overtime_approvals",
    )

    op.drop_table("tpc_overtime_approvals")
