"""employee document expiries: expiry date per 201 Employment File (HR Dashboard)

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "b6c7d8e9f0a1"
down_revision = "a5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_employee_document_expiries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("tpc_employees.id"), nullable=False),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("has_expiry", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("employee_id", "document_type", name="uq_employee_document_expiry"),
    )
    op.create_index(
        "ix_tpc_employee_document_expiries_employee_id",
        "tpc_employee_document_expiries",
        ["employee_id"],
    )


def downgrade():
    op.drop_index(
        "ix_tpc_employee_document_expiries_employee_id",
        table_name="tpc_employee_document_expiries",
    )
    op.drop_table("tpc_employee_document_expiries")
