"""add user revisions table

Revision ID: e4b016e4d0d9
Revises: ae3ed60b3564
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4b016e4d0d9'
down_revision: Union[str, Sequence[str], None] = 'ae3ed60b3564'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Audit trail for user role/active-status changes. See
    # app/models/user_revision.py and update_user_service() in
    # app/services/user_service.py.
    op.create_table(
        "tpc_user_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("field_changed", sa.String(length=50), nullable=False),
        sa.Column("old_value", sa.String(length=50), nullable=True),
        sa.Column("new_value", sa.String(length=50), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["tpc_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["tpc_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tpc_user_revisions_id"),
        "tpc_user_revisions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tpc_user_revisions_user_id"),
        "tpc_user_revisions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tpc_user_revisions_user_id"), table_name="tpc_user_revisions")
    op.drop_index(op.f("ix_tpc_user_revisions_id"), table_name="tpc_user_revisions")
    op.drop_table("tpc_user_revisions")
