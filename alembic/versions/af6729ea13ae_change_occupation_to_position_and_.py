"""change occupation to position and modify applicant employment

Revision ID: af6729ea13ae
Revises: b78a79f82f8e
Create Date: 2026-04-15 14:09:23.106981

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "af6729ea13ae"
down_revision: Union[str, Sequence[str], None] = "b78a79f82f8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_applicant_employment_history",
        sa.Column("reason_for_leaving", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "tpc_applicant_employment_history",
        sa.Column("salary_history", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "tpc_applicant_employment_history",
        sa.Column("salary_type", sa.String(length=50), nullable=True),
    )

    op.add_column(
        "tpc_applicant_references",
        sa.Column("position", sa.String(length=150), nullable=True),
    )

    op.execute("""
        UPDATE tpc_applicant_references
        SET position = occupation
        WHERE occupation IS NOT NULL
    """)

    op.drop_column("tpc_applicant_references", "occupation")


def downgrade() -> None:
    op.add_column(
        "tpc_applicant_references",
        sa.Column("occupation", sa.String(length=150), nullable=True),
    )

    op.execute("""
        UPDATE tpc_applicant_references
        SET occupation = position
        WHERE position IS NOT NULL
    """)

    op.drop_column("tpc_applicant_references", "position")

    op.drop_column("tpc_applicant_employment_history", "salary_type")
    op.drop_column("tpc_applicant_employment_history", "salary_history")
    op.drop_column("tpc_applicant_employment_history", "reason_for_leaving")
    # ### end Alembic commands ###
