"""added salary column in onboarding

Revision ID: bfdf300c8537
Revises: 59ef27f3f90c
Create Date: 2026-04-12 12:14:22.739296

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "bfdf300c8537"
down_revision: Union[str, Sequence[str], None] = "59ef27f3f90c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "tpc_applicant_onboarding",
        sa.Column("current_salary", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "tpc_applicant_onboarding",
        sa.Column("expected_salary", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "tpc_applicant_onboarding",
        sa.Column("salary_type", sa.String(length=50), nullable=True),
    )


def downgrade():
    op.drop_column("tpc_applicant_onboarding", "salary_type")
    op.drop_column("tpc_applicant_onboarding", "expected_salary")
    op.drop_column("tpc_applicant_onboarding", "current_salary")