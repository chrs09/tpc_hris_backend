"""customer chart: customers as a tree, customer tiers, store/trip links

Revision ID: c8d9e0f1a2b3
Revises: b6c7d8e9f0a1
Create Date: 2026-11-11

Seeds the chart from today's data so nothing changes for dispatchers:
one customer "Coca-Cola" with
  T1 -- hubs (plants / DCs / yards), rate from lane rates
  T2 -- every customer location that isn't a hub, rate from trip profile
Supplier-only locations stay unassigned.
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_customers", sa.Column("parent_id", sa.Integer(), sa.ForeignKey("tpc_customers.id"), nullable=True))
    op.create_index("ix_tpc_customers_parent_id", "tpc_customers", ["parent_id"])
    op.add_column("tpc_customers", sa.Column("code", sa.String(30), nullable=True))
    op.add_column("tpc_customers", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("tpc_customers", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "tpc_customer_tiers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("tpc_customers.id"), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("rate_source", sa.String(20), nullable=False, server_default="trip_profile"),
        sa.Column("truck_type_ids", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tpc_customer_tiers_customer_id", "tpc_customer_tiers", ["customer_id"])

    op.add_column("tpc_stores", sa.Column("customer_tier_id", sa.Integer(), sa.ForeignKey("tpc_customer_tiers.id"), nullable=True))
    op.create_index("ix_tpc_stores_customer_tier_id", "tpc_stores", ["customer_tier_id"])

    op.add_column("tpc_trips", sa.Column("customer_id", sa.Integer(), sa.ForeignKey("tpc_customers.id"), nullable=True))
    op.create_index("ix_tpc_trips_customer_id", "tpc_trips", ["customer_id"])
    op.add_column("tpc_trips", sa.Column("customer_tier_id", sa.Integer(), sa.ForeignKey("tpc_customer_tiers.id"), nullable=True))
    op.create_index("ix_tpc_trips_customer_tier_id", "tpc_trips", ["customer_tier_id"])

    # ---- seed: Coca-Cola with T1 (hub lanes) and T2 (outlets)
    bind = op.get_bind()
    now = datetime.utcnow()
    bind.execute(
        sa.text(
            "INSERT INTO tpc_customers (name, is_active, sort_order, created_at, updated_at) "
            "VALUES ('Coca-Cola', 1, 0, :now, :now)"
        ),
        {"now": now},
    )
    customer_id = bind.execute(
        sa.text("SELECT id FROM tpc_customers WHERE name = 'Coca-Cola' ORDER BY id DESC LIMIT 1")
    ).scalar()
    for order, (name, description, source) in enumerate(
        (
            ("T1", "Plant / DC lanes", "lane"),
            ("T2", "Outlet deliveries", "trip_profile"),
        )
    ):
        bind.execute(
            sa.text(
                "INSERT INTO tpc_customer_tiers "
                "(customer_id, name, description, rate_source, sort_order, is_active, created_at, updated_at) "
                "VALUES (:c, :n, :d, :s, :o, 1, :now, :now)"
            ),
            {"c": customer_id, "n": name, "d": description, "s": source, "o": order, "now": now},
        )
    tiers = dict(
        bind.execute(
            sa.text("SELECT name, id FROM tpc_customer_tiers WHERE customer_id = :c"),
            {"c": customer_id},
        ).fetchall()
    )
    bind.execute(
        sa.text("UPDATE tpc_stores SET customer_tier_id = :t WHERE is_hub = 1"),
        {"t": tiers["T1"]},
    )
    bind.execute(
        sa.text(
            "UPDATE tpc_stores SET customer_tier_id = :t "
            "WHERE is_hub = 0 AND is_customer = 1"
        ),
        {"t": tiers["T2"]},
    )


def downgrade():
    op.drop_index("ix_tpc_trips_customer_tier_id", table_name="tpc_trips")
    op.drop_column("tpc_trips", "customer_tier_id")
    op.drop_index("ix_tpc_trips_customer_id", table_name="tpc_trips")
    op.drop_column("tpc_trips", "customer_id")
    op.drop_index("ix_tpc_stores_customer_tier_id", table_name="tpc_stores")
    op.drop_column("tpc_stores", "customer_tier_id")
    op.drop_index("ix_tpc_customer_tiers_customer_id", table_name="tpc_customer_tiers")
    op.drop_table("tpc_customer_tiers")
    op.drop_column("tpc_customers", "sort_order")
    op.drop_column("tpc_customers", "notes")
    op.drop_column("tpc_customers", "code")
    op.drop_index("ix_tpc_customers_parent_id", table_name="tpc_customers")
    op.drop_column("tpc_customers", "parent_id")
