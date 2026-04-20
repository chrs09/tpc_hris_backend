"""modify employee reference and employment history

Revision ID: 5396b6c4ee38
Revises: 8d649c35bf9a
Create Date: 2026-04-20 13:24:24.012490
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "5396b6c4ee38"
down_revision: Union[str, Sequence[str], None] = "8d649c35bf9a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename occupation -> position
    op.alter_column(
        "tpc_employee_references",
        "occupation",
        new_column_name="position",
        existing_type=sa.String(length=150),
        existing_nullable=True,
    )

    # Add missing employee employment history fields
    op.add_column(
        "tpc_employee_employment_history",
        sa.Column("reason_for_leaving", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "tpc_employee_employment_history",
        sa.Column("salary_history", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "tpc_employee_employment_history",
        sa.Column("salary_type", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    # Remove added employment history fields
    op.drop_column("tpc_employee_employment_history", "salary_type")
    op.drop_column("tpc_employee_employment_history", "salary_history")
    op.drop_column("tpc_employee_employment_history", "reason_for_leaving")

    # Rename position -> occupation
    op.alter_column(
        "tpc_employee_references",
        "position",
        new_column_name="occupation",
        existing_type=sa.String(length=150),
        existing_nullable=True,
    )
