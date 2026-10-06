"""ticket helpdesk: categories, routing, public tickets

- tpc_ticket_categories: what a ticket is about and which Org Chart unit
  handles it (seeded with five starter categories, matched to units by
  name where they exist -- edit them on the Tickets page).
- tpc_tickets: category, source (internal / public), the public
  requester's details, a history timeline (JSON); created_by is now
  optional (public tickets have no user).
- tpc_ticket_comments: to_customer (reply sent to the public requester).

Revision ID: c8e2a4b6d791
Revises: b5d7f9a1c369
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "c8e2a4b6d791"
down_revision = "b5d7f9a1c369"
branch_labels = None
depends_on = None

# (name, description, unit name patterns tried in order, public)
SEED = [
    ("Trip / Delivery", "Deliveries, trips, drivers and store drop-offs.", ["%coordinator%", "%trip%", "%operation%"], True),
    ("Customer complaint", "Complaints and feedback from customers and stores.", ["%operation%", "%coordinator%"], True),
    ("Technical / System", "Problems with the app or website, logins, errors.", ["it", "%it%"], True),
    ("Payroll / HR", "Pay, attendance, leave and employee records.", ["hr", "%hr%"], False),
    ("Fleet / Vehicle", "Truck problems, repairs, fuel.", ["%motorpool%", "%fleet%"], False),
]


def upgrade():
    op.create_table(
        "tpc_ticket_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("org_unit_id", sa.Integer(), sa.ForeignKey("tpc_org_units.id"), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.add_column("tpc_tickets", sa.Column("category_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tpc_tickets_category", "tpc_tickets", "tpc_ticket_categories", ["category_id"], ["id"]
    )
    op.add_column("tpc_tickets", sa.Column("source", sa.String(10), nullable=False, server_default="internal"))
    op.add_column("tpc_tickets", sa.Column("requester_name", sa.String(150), nullable=True))
    op.add_column("tpc_tickets", sa.Column("requester_phone", sa.String(50), nullable=True))
    op.add_column("tpc_tickets", sa.Column("requester_email", sa.String(150), nullable=True))
    op.add_column("tpc_tickets", sa.Column("requester_company", sa.String(150), nullable=True))
    op.add_column("tpc_tickets", sa.Column("requester_ip", sa.String(64), nullable=True))
    op.add_column("tpc_tickets", sa.Column("history", sa.Text(), nullable=True))
    op.alter_column("tpc_tickets", "created_by_user_id", existing_type=sa.Integer(), nullable=True)
    op.add_column(
        "tpc_ticket_comments",
        sa.Column("to_customer", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    conn = op.get_bind()
    for order, (name, description, patterns, public) in enumerate(SEED):
        unit_id = None
        for pattern in patterns:
            row = conn.execute(
                sa.text("SELECT id FROM tpc_org_units WHERE LOWER(name) LIKE :p ORDER BY id LIMIT 1"),
                {"p": pattern},
            ).first()
            if row:
                unit_id = row[0]
                break
        conn.execute(
            sa.text(
                "INSERT INTO tpc_ticket_categories "
                "(name, description, org_unit_id, is_public, is_active, sort_order, created_at) "
                "VALUES (:n, :d, :u, :pub, 1, :o, NOW())"
            ),
            {"n": name, "d": description, "u": unit_id, "pub": 1 if public else 0, "o": order},
        )


def downgrade():
    op.drop_column("tpc_ticket_comments", "to_customer")
    for col in ("history", "requester_ip", "requester_company", "requester_email",
                "requester_phone", "requester_name", "source"):
        op.drop_column("tpc_tickets", col)
    op.drop_constraint("fk_tpc_tickets_category", "tpc_tickets", type_="foreignkey")
    op.drop_column("tpc_tickets", "category_id")
    op.drop_table("tpc_ticket_categories")
