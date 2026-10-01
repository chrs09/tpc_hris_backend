"""banks

Banks for the employee 201 form, managed in Settings instead of
hard-coded. Seeded with the list the form had, plus Maya.

Revision ID: a9c3e5f7b812
Revises: f8b4d2e6a931
Create Date: 2026-10-01
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "a9c3e5f7b812"
down_revision = "f8b4d2e6a931"
branch_labels = None
depends_on = None

SEED = [
    "BDO",
    "GoTyme",
    "BPI",
    "Metrobank",
    "UnionBank",
    "Gcash",
    "Cebuana",
    "Maribank",
    "Maya",
    "Other",
]


def upgrade():
    table = op.create_table(
        "tpc_banks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    now = datetime.utcnow()
    op.bulk_insert(
        table, [{"name": name, "is_active": True, "created_at": now} for name in SEED]
    )


def downgrade():
    op.drop_table("tpc_banks")
