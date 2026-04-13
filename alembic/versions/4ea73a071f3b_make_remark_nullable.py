"""make remark nullable

Revision ID: 4ea73a071f3b
Revises: bfdf300c8537
Create Date: 2026-04-12 23:12:17.353094

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "4ea73a071f3b"
down_revision: Union[str, Sequence[str], None] = "bfdf300c8537"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "tpc_applicant_remarks",
        "remark",
        existing_type=mysql.TEXT(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "tpc_applicant_remarks",
        "remark",
        existing_type=mysql.TEXT(),
        nullable=False,
    )