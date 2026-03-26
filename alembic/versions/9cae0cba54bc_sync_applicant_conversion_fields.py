"""sync applicant conversion fields

Revision ID: 9cae0cba54bc
Revises: c532adb24c98
Create Date: 2026-03-26 13:19:43.160619

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9cae0cba54bc"
down_revision: Union[str, Sequence[str], None] = "c532adb24c98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_applicants",
        sa.Column(
            "is_converted_to_employee",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "tpc_applicants",
        sa.Column("employee_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tpc_applicants",
        sa.Column("hired_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "tpc_applicants",
        sa.Column("converted_at", sa.DateTime(), nullable=True),
    )
    op.create_foreign_key(
        "fk_tpc_applicants_employee_id",
        "tpc_applicants",
        "tpc_employees",
        ["employee_id"],
        ["id"],
    )

    op.alter_column(
        "tpc_applicants",
        "is_converted_to_employee",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_tpc_applicants_employee_id",
        "tpc_applicants",
        type_="foreignkey",
    )
    op.drop_column("tpc_applicants", "converted_at")
    op.drop_column("tpc_applicants", "hired_at")
    op.drop_column("tpc_applicants", "employee_id")
    op.drop_column("tpc_applicants", "is_converted_to_employee")