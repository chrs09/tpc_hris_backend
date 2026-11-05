"""stores: is_customer flag (Customer / Supplier / both on the Customers page)

Every existing location stays a customer (it was one before); a
location can now be supplier-only.

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_stores",
        sa.Column("is_customer", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade():
    op.drop_column("tpc_stores", "is_customer")
