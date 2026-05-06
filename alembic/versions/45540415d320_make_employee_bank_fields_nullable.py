"""make Employee Bank fields nullable

Revision ID: 45540415d320
Revises: b013953cdb41
Create Date: 2026-05-06 13:23:20.259040
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "45540415d320"
down_revision: Union[str, Sequence[str], None] = "b013953cdb41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "tpc_employee_bank",
        "bank_type",
        existing_type=mysql.VARCHAR(length=100),
        nullable=True,
    )

    op.alter_column(
        "tpc_employee_bank",
        "account_name",
        existing_type=mysql.VARCHAR(length=150),
        nullable=True,
    )

    op.alter_column(
        "tpc_employee_bank",
        "account_number",
        existing_type=mysql.VARCHAR(length=100),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "tpc_employee_bank",
        "account_number",
        existing_type=mysql.VARCHAR(length=100),
        nullable=False,
    )

    op.alter_column(
        "tpc_employee_bank",
        "account_name",
        existing_type=mysql.VARCHAR(length=150),
        nullable=False,
    )

    op.alter_column(
        "tpc_employee_bank",
        "bank_type",
        existing_type=mysql.VARCHAR(length=100),
        nullable=False,
    )
