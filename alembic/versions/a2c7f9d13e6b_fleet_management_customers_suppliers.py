"""fleet management customers and suppliers

Revision ID: a2c7f9d13e6b
Revises: 414f9840c17e
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2c7f9d13e6b"
down_revision: Union[str, Sequence[str], None] = "414f9840c17e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tpc_customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("contact_person", sa.String(length=150), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=150), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tpc_customers_id"), "tpc_customers", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_tpc_customers_name"), "tpc_customers", ["name"], unique=False
    )

    op.create_table(
        "tpc_suppliers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("contact_person", sa.String(length=150), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=150), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tpc_suppliers_id"), "tpc_suppliers", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_tpc_suppliers_name"), "tpc_suppliers", ["name"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tpc_suppliers_name"), table_name="tpc_suppliers")
    op.drop_index(op.f("ix_tpc_suppliers_id"), table_name="tpc_suppliers")
    op.drop_table("tpc_suppliers")

    op.drop_index(op.f("ix_tpc_customers_name"), table_name="tpc_customers")
    op.drop_index(op.f("ix_tpc_customers_id"), table_name="tpc_customers")
    op.drop_table("tpc_customers")
