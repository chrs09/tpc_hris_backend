"""add mobile page access table and employees.has_custom_mobile_access

Revision ID: b8d4f1a6c9e7
Revises: a7c2e5f8b1d3
Create Date: 2026-09-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b8d4f1a6c9e7"
down_revision = "a7c2e5f8b1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tpc_employees",
        sa.Column(
            "has_custom_mobile_access",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "tpc_mobile_page_access",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "employee_id",
            sa.Integer(),
            sa.ForeignKey("tpc_employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_key", sa.String(50), nullable=False),
        sa.Column(
            "granted_by_user_id",
            sa.Integer(),
            sa.ForeignKey("tpc_users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "employee_id", "page_key", name="uq_employee_mobile_page"
        ),
    )


def downgrade() -> None:
    op.drop_table("tpc_mobile_page_access")
    op.drop_column("tpc_employees", "has_custom_mobile_access")
