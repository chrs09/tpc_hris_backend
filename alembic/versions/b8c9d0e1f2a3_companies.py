"""companies table + the company a vehicle unit belongs to

Administrator -> Companies (superadmin only) keeps the companies; Fleet
Management's Add / Edit Vehicle Unit picks one (superadmin only).
Nothing else uses it yet.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tpc_companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("code", sa.String(30), nullable=True),
        sa.Column("tin", sa.String(30), nullable=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("contact_person", sa.String(150), nullable=True),
        sa.Column("contact_number", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("tpc_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("name", name="uq_tpc_companies_name"),
    )
    op.create_index("ix_tpc_companies_id", "tpc_companies", ["id"])

    op.add_column("tpc_vehicle_units", sa.Column("company_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tpc_vehicle_units_company_id",
        "tpc_vehicle_units",
        "tpc_companies",
        ["company_id"],
        ["id"],
    )
    op.create_index("ix_tpc_vehicle_units_company_id", "tpc_vehicle_units", ["company_id"])


def downgrade():
    op.drop_index("ix_tpc_vehicle_units_company_id", table_name="tpc_vehicle_units")
    op.drop_constraint("fk_tpc_vehicle_units_company_id", "tpc_vehicle_units", type_="foreignkey")
    op.drop_column("tpc_vehicle_units", "company_id")
    op.drop_index("ix_tpc_companies_id", table_name="tpc_companies")
    op.drop_table("tpc_companies")
