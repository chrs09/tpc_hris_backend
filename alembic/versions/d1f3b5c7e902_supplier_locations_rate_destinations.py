"""supplier locations and outlet destinations for driver rates

- tpc_stores.is_supplier: a location that is also a supplier -- shows in
  Suppliers, can be a trip's start point and a driver rate's "From".
- tpc_suppliers.store_id: the supplier's map location (that makes it a
  customer / delivery point too).
- tpc_trip_rate_rules.destination_store_id: a rate for one exact outlet
  (beats an area rate).

Revision ID: d1f3b5c7e902
Revises: c8e2a4b6d791
Create Date: 2026-10-06
"""

from alembic import op
import sqlalchemy as sa


revision = "d1f3b5c7e902"
down_revision = "c8e2a4b6d791"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_stores",
        sa.Column("is_supplier", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("tpc_suppliers", sa.Column("store_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tpc_suppliers_store", "tpc_suppliers", "tpc_stores", ["store_id"], ["id"]
    )
    op.add_column(
        "tpc_trip_rate_rules", sa.Column("destination_store_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_tpc_trip_rate_rules_dest_store",
        "tpc_trip_rate_rules",
        "tpc_stores",
        ["destination_store_id"],
        ["id"],
    )
    op.create_index(
        "ix_tpc_trip_rate_rules_destination_store_id",
        "tpc_trip_rate_rules",
        ["destination_store_id"],
    )


def downgrade():
    op.drop_constraint("fk_tpc_trip_rate_rules_dest_store", "tpc_trip_rate_rules", type_="foreignkey")
    op.drop_index("ix_tpc_trip_rate_rules_destination_store_id", table_name="tpc_trip_rate_rules")
    op.drop_column("tpc_trip_rate_rules", "destination_store_id")
    op.drop_constraint("fk_tpc_suppliers_store", "tpc_suppliers", type_="foreignkey")
    op.drop_column("tpc_suppliers", "store_id")
    op.drop_column("tpc_stores", "is_supplier")
