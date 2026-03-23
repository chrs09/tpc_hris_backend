"""create tpc_applicants table

Revision ID: 75716e1c7e34
Revises: c853921c2599
Create Date: 2026-03-21 23:50:59.061825

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "75716e1c7e34"
down_revision: Union[str, Sequence[str], None] = "c853921c2599"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tpc_applicants",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("contact_number", sa.String(length=50), nullable=False),
        sa.Column("position_applied", sa.String(length=100), nullable=False),
        sa.Column("cv_file", sa.String(length=255), nullable=True),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="pending"
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_index("ix_tpc_applicants_email", "tpc_applicants", ["email"])
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_index("ix_tpc_applicants_email", table_name="tpc_applicants")
    op.drop_table("tpc_applicants")
    # ### end Alembic commands ###
