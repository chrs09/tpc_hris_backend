"""users: clear placeholder emails ("N/A" etc.) copied from the 201 file

Data only. The 201 email sync (e4b5c6d7f8a9) copied whatever was in the
employee's email -- including placeholders like "N/A" -- onto the login
account, which broke the Users list. Anything that isn't a real address
is set back to NULL (the column is nullable; login is by username).

Revision ID: f5c6d7e8a9b0
Revises: e4b5c6d7f8a9
Create Date: 2026-10-27
"""

import re

import sqlalchemy as sa
from alembic import op

revision = "f5c6d7e8a9b0"
down_revision = "e4b5c6d7f8a9"
branch_labels = None
depends_on = None

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, email FROM tpc_users WHERE email IS NOT NULL")
    ).fetchall()
    for user_id, email in rows:
        if not _EMAIL_RE.match((email or "").strip()):
            conn.execute(
                sa.text("UPDATE tpc_users SET email = NULL WHERE id = :id"),
                {"id": user_id},
            )


def downgrade():
    # Data cleanup only; the placeholders aren't restored.
    pass
