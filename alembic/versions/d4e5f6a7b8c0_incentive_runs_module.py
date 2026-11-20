"""incentive runs module key

Incentive Runs gets its own tick on the Org Chart (payroll.incentive_runs)
instead of riding on Incentive Policies. Everyone who has Incentive
Policies today keeps seeing Incentive Runs: their grant (and any role
default) is copied to the new key.

Revision ID: d4e5f6a7b8c0
Revises: c3d4e5f6a7b9
Create Date: 2026-11-20
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c0"
down_revision = "c3d4e5f6a7b9"
branch_labels = None
depends_on = None

OLD = "payroll.incentive_policies"
NEW = "payroll.incentive_runs"


def upgrade():
    op.execute(
        f"""
        INSERT INTO tpc_employee_module_access (employee_id, module_key, can_edit, granted_by_user_id, created_at)
        SELECT a.employee_id, '{NEW}', a.can_edit, a.granted_by_user_id, CURRENT_TIMESTAMP
        FROM tpc_employee_module_access a
        WHERE a.module_key = '{OLD}'
          AND NOT EXISTS (
            SELECT 1 FROM tpc_employee_module_access b
            WHERE b.employee_id = a.employee_id AND b.module_key = '{NEW}'
          )
        """
    )

    # Role defaults (Administrator -> role default access): JSON lists.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT role, module_keys, read_only_keys FROM tpc_role_module_defaults")
    ).fetchall()
    for role, module_keys, read_only_keys in rows:
        keys = json.loads(module_keys or "[]")
        read_only = json.loads(read_only_keys or "[]")
        if OLD not in keys or NEW in keys:
            continue
        keys.append(NEW)
        if OLD in read_only and NEW not in read_only:
            read_only.append(NEW)
        conn.execute(
            sa.text(
                "UPDATE tpc_role_module_defaults SET module_keys = :k, read_only_keys = :r WHERE role = :role"
            ),
            {"k": json.dumps(keys), "r": json.dumps(read_only), "role": role},
        )


def downgrade():
    op.execute(f"DELETE FROM tpc_employee_module_access WHERE module_key = '{NEW}'")
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT role, module_keys, read_only_keys FROM tpc_role_module_defaults")
    ).fetchall()
    for role, module_keys, read_only_keys in rows:
        keys = [k for k in json.loads(module_keys or "[]") if k != NEW]
        read_only = [k for k in json.loads(read_only_keys or "[]") if k != NEW]
        conn.execute(
            sa.text(
                "UPDATE tpc_role_module_defaults SET module_keys = :k, read_only_keys = :r WHERE role = :role"
            ),
            {"k": json.dumps(keys), "r": json.dumps(read_only), "role": role},
        )
