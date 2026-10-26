"""users: take the email from the employee's 201 record (source of truth)

Data only: copies each employee's email to their linked user account(s)
when it differs -- skipped when another account already uses that email
(the email column is unique).

Revision ID: e4b5c6d7f8a9
Revises: d3a4b5c6e7f9
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

revision = "e4b5c6d7f8a9"
down_revision = "d3a4b5c6e7f9"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT u.id, e.email FROM tpc_users u "
            "JOIN tpc_employees e ON e.id = u.employee_id "
            "WHERE e.email IS NOT NULL AND e.email <> '' "
            "AND (u.email IS NULL OR u.email <> e.email)"
        )
    ).fetchall()
    for user_id, email in rows:
        taken = conn.execute(
            sa.text("SELECT id FROM tpc_users WHERE email = :email AND id <> :id"),
            {"email": email, "id": user_id},
        ).first()
        if taken:
            continue
        conn.execute(
            sa.text("UPDATE tpc_users SET email = :email WHERE id = :id"),
            {"email": email, "id": user_id},
        )


def downgrade():
    # Data sync only; the old account emails aren't kept.
    pass
