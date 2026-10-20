"""onboarding: middle name, suffix and bank details (same as Employee 201)

Revision ID: f9c0d1e2a3b4
Revises: e8b9c0d1f2a3
Create Date: 2026-10-20
"""

import sqlalchemy as sa
from alembic import op

revision = "f9c0d1e2a3b4"
down_revision = "e8b9c0d1f2a3"
branch_labels = None
depends_on = None

COLUMNS = [
    ("middle_name", sa.String(100)),
    ("suffix", sa.String(50)),
    ("bank_type", sa.String(100)),
    ("account_name", sa.String(150)),
    ("account_number", sa.String(100)),
]


def upgrade():
    for name, type_ in COLUMNS:
        op.add_column("tpc_applicant_onboarding", sa.Column(name, type_, nullable=True))


def downgrade():
    for name, _ in reversed(COLUMNS):
        op.drop_column("tpc_applicant_onboarding", name)
