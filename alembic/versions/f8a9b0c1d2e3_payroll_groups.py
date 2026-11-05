"""payroll groups: run payroll per group instead of per department

- tpc_payroll_groups, seeded with the 6 groups:
    Fixed monthly - semi monthly      Admin (Monthly)
    Fixed daily - semi monthly        Admin (Daily)
    Driver - per trip - semi monthly  CpdcDriver, CdcDriver
    Helper - per trip - semi monthly  CpdcHelper, CdcHelper
    Driver - per trip - weekly        Dumptruck, WingvanDriver
    Fixed daily - weekly              Labor, Motorpool, Yard
- each group's cutoff rule is copied from a member department's rule
  (the department rules stay, for payrolls from before groups).

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-11-04
"""

import json
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None

GROUPS = [
    ("Fixed monthly - semi monthly", "fixed_monthly", ["Admin"], "Monthly"),
    ("Fixed daily - semi monthly", "fixed_daily", ["Admin"], "Daily"),
    ("Driver - per trip - semi monthly", "per_trip_driver", ["CpdcDriver", "CdcDriver"], None),
    ("Helper - per trip - semi monthly", "per_trip_helper", ["CpdcHelper", "CdcHelper"], None),
    ("Driver - per trip - weekly", "per_trip_driver", ["Dumptruck", "WingvanDriver"], None),
    ("Fixed daily - weekly", "fixed_daily", ["Labor", "Motorpool", "Yard"], None),
]

RULE_FIELDS = (
    "schedule_type",
    "first_start_day",
    "second_start_day",
    "first_payout_day",
    "second_payout_day",
    "week_start_day",
    "payout_offset_days",
)


def upgrade():
    op.create_table(
        "tpc_payroll_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("pay_basis", sa.String(20), nullable=False),
        sa.Column("departments", sa.Text(), nullable=False),
        sa.Column("payroll_type", sa.String(20), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tpc_payroll_groups_id", "tpc_payroll_groups", ["id"])
    op.create_index("ix_tpc_payroll_groups_name", "tpc_payroll_groups", ["name"], unique=True)

    conn = op.get_bind()
    now = datetime.utcnow()
    rules = {
        row[0].lower(): row
        for row in conn.execute(
            sa.text(
                "SELECT department, " + ", ".join(RULE_FIELDS) + " FROM tpc_payroll_cutoff_rules"
            )
        ).fetchall()
    }
    for order, (name, basis, departments, ptype) in enumerate(GROUPS, start=1):
        conn.execute(
            sa.text(
                "INSERT INTO tpc_payroll_groups (name, pay_basis, departments, payroll_type, "
                "sort_order, is_active, created_at, updated_at) "
                "VALUES (:name, :basis, :departments, :ptype, :order, 1, :now, :now)"
            ),
            {
                "name": name,
                "basis": basis,
                "departments": json.dumps(departments),
                "ptype": ptype,
                "order": order,
                "now": now,
            },
        )
        # The group's cutoff: the first member department that has one.
        source = next((rules[d.lower()] for d in departments if d.lower() in rules), None)
        if source is None:
            continue  # shows "Not set" on the Payroll Groups page
        values = dict(zip(RULE_FIELDS, source[1:]))
        conn.execute(
            sa.text(
                "INSERT INTO tpc_payroll_cutoff_rules (department, "
                + ", ".join(RULE_FIELDS)
                + ", updated_at) VALUES (:department, "
                + ", ".join(f":{f}" for f in RULE_FIELDS)
                + ", :now)"
            ),
            {"department": name, **values, "now": now},
        )


def downgrade():
    conn = op.get_bind()
    for name, *_ in GROUPS:
        conn.execute(
            sa.text("DELETE FROM tpc_payroll_cutoff_rules WHERE department = :name"),
            {"name": name},
        )
    op.drop_index("ix_tpc_payroll_groups_name", table_name="tpc_payroll_groups")
    op.drop_index("ix_tpc_payroll_groups_id", table_name="tpc_payroll_groups")
    op.drop_table("tpc_payroll_groups")
