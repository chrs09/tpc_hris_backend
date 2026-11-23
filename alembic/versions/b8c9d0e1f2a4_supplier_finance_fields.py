"""suppliers: type, category, TIN, VAT registered (Finance)

Revision ID: b8c9d0e1f2a4
Revises: a7b8c9d0e1f3
Create Date: 2026-11-23
"""

import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a4"
down_revision = "a7b8c9d0e1f3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_suppliers", sa.Column("supplier_type", sa.String(20), nullable=True))
    op.add_column("tpc_suppliers", sa.Column("category", sa.String(60), nullable=True))
    op.add_column("tpc_suppliers", sa.Column("tin", sa.String(20), nullable=True))
    op.add_column("tpc_suppliers", sa.Column("vat_registered", sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column("tpc_suppliers", "vat_registered")
    op.drop_column("tpc_suppliers", "tin")
    op.drop_column("tpc_suppliers", "category")
    op.drop_column("tpc_suppliers", "supplier_type")
