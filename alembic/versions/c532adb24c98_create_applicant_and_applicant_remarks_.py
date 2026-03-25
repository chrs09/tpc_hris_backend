"""create applicant and applicant remarks table

Revision ID: c532adb24c98
Revises: 75716e1c7e34
Create Date: 2026-03-25 11:14:31.366961

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'c532adb24c98'
down_revision: Union[str, Sequence[str], None] = '75716e1c7e34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tpc_applicant_remarks",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("applicant_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("remark", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["applicant_id"], ["tpc_applicants.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["tpc_users.id"]),
    )
    op.create_index(
        op.f("ix_tpc_applicant_remarks_id"),
        "tpc_applicant_remarks",
        ["id"],
        unique=False,
    )

    op.drop_column("tpc_applicants", "cv_file")


def downgrade() -> None:
    op.add_column(
        "tpc_applicants",
        sa.Column("cv_file", sa.String(length=255), nullable=True),
    )

    op.drop_index(
        op.f("ix_tpc_applicant_remarks_id"),
        table_name="tpc_applicant_remarks",
    )
    op.drop_table("tpc_applicant_remarks")
    # ### end Alembic commands ###
