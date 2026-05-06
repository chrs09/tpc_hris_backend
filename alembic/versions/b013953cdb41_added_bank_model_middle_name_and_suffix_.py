"""added bank model, middle name and suffix for employee applicant

Revision ID: b013953cdb41
Revises: 5396b6c4ee38
Create Date: 2026-05-05 15:23:10.005425
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b013953cdb41"
down_revision: Union[str, Sequence[str], None] = "5396b6c4ee38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_employees",
        sa.Column("middle_name", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "tpc_employees",
        sa.Column("suffix", sa.String(length=20), nullable=True),
    )

    op.add_column(
        "tpc_applicants",
        sa.Column("middle_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "tpc_applicants",
        sa.Column("suffix", sa.String(length=50), nullable=True),
    )

    op.create_table(
        "tpc_employee_bank",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("bank_type", sa.String(length=100), nullable=False),
        sa.Column("account_name", sa.String(length=150), nullable=False),
        sa.Column("account_number", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["tpc_employees.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id"),
    )

    op.create_index(
        op.f("ix_tpc_employee_bank_id"),
        "tpc_employee_bank",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tpc_employee_bank_id"),
        table_name="tpc_employee_bank",
    )
    op.drop_table("tpc_employee_bank")

    op.drop_column("tpc_applicants", "suffix")
    op.drop_column("tpc_applicants", "middle_name")

    op.drop_column("tpc_employees", "suffix")
    op.drop_column("tpc_employees", "middle_name")
