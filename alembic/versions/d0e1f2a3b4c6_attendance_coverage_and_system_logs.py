"""Org Chart "Also covers" (attendance coverage) + System Logs table

Revision ID: d0e1f2a3b4c6
Revises: c9d0e1f2a3b5
Create Date: 2026-11-25
"""

import sqlalchemy as sa
from alembic import op

revision = "d0e1f2a3b4c6"
down_revision = "c9d0e1f2a3b5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_org_units", sa.Column("also_covers", sa.Text(), nullable=True))

    op.create_table(
        "tpc_activity_logs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), nullable=True, index=True),
        sa.Column("username", sa.String(50), nullable=True),
        sa.Column("role", sa.String(30), nullable=True),
        sa.Column("impersonated_by", sa.Integer(), nullable=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(500), nullable=False, index=True),
        sa.Column("query", sa.String(1000), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("summary", sa.String(255), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("changes", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_table("tpc_activity_logs")
    op.drop_column("tpc_org_units", "also_covers")
