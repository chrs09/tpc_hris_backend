"""cash advance reference no: CA-<year>-<id>, backfilled for existing ones

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-11-18
"""

import sqlalchemy as sa
from alembic import op

revision = "f0a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tpc_cash_advance_requests",
        sa.Column("reference_no", sa.String(20), nullable=True),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, created_at FROM tpc_cash_advance_requests ORDER BY id")
    ).fetchall()
    for row_id, created_at in rows:
        year = str(created_at)[:4] if created_at else "0000"
        bind.execute(
            sa.text("UPDATE tpc_cash_advance_requests SET reference_no = :ref WHERE id = :id"),
            {"ref": f"CA-{year}-{row_id:04d}", "id": row_id},
        )
    op.create_index(
        "ix_tpc_cash_advance_requests_reference_no",
        "tpc_cash_advance_requests",
        ["reference_no"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_tpc_cash_advance_requests_reference_no", table_name="tpc_cash_advance_requests")
    op.drop_column("tpc_cash_advance_requests", "reference_no")
