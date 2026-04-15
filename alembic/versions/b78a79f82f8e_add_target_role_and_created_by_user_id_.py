"""add target_role and created_by_user_id to applicant question

Revision ID: b78a79f82f8e
Revises: 0dac35916efa
Create Date: 2026-04-14 11:53:37.166459

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b78a79f82f8e'
down_revision: Union[str, Sequence[str], None] = '0dac35916efa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tpc_applicant_questions",
        sa.Column("target_role", sa.String(length=50), nullable=True),
    )

    op.add_column(
        "tpc_applicant_questions",
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
    )

    op.create_index(
        "ix_tpc_applicant_questions_target_role",
        "tpc_applicant_questions",
        ["target_role"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_applicant_questions_created_by_user",
        "tpc_applicant_questions",
        "tpc_users",
        ["created_by_user_id"],
        ["id"],
    )

    # Optional backfill for existing rows so target_role won't stay null.
    # Adjust this value if you want something else like 'all'.
    op.execute(
        "UPDATE tpc_applicant_questions SET target_role = 'all' WHERE target_role IS NULL"
    )

    op.alter_column(
        "tpc_applicant_questions",
        "target_role",
        existing_type=sa.String(length=50),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_applicant_questions_created_by_user",
        "tpc_applicant_questions",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_tpc_applicant_questions_target_role",
        table_name="tpc_applicant_questions",
    )

    op.drop_column("tpc_applicant_questions", "created_by_user_id")
    op.drop_column("tpc_applicant_questions", "target_role")