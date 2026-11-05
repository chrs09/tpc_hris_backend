"""driver / helper accounts: role from the department

Accounts made by Bulk Create Accounts were all role Employee, so drivers
and helpers didn't get the Driver / Helper role (and their trip app).
Sets Driver / Helper on Employee-role accounts whose employee is in a
driver / helper department (app/services/user_roles.py). Other roles
(admin, coordinator, ...) are left alone.

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-11-05
"""

from alembic import op

revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None

DRIVER_DEPARTMENTS = ("cdcdriver", "cpdcdriver", "wingvandriver")
HELPER_DEPARTMENTS = ("cdchelper", "cpdchelper")


def _set_role(role: str, departments: tuple[str, ...]) -> None:
    names = ", ".join(f"'{d}'" for d in departments)
    op.execute(
        f"UPDATE tpc_users SET role = '{role}' "
        "WHERE role = 'EMPLOYEE' AND employee_id IN ("
        "SELECT id FROM tpc_employees "
        f"WHERE LOWER(TRIM(department)) IN ({names}))"
    )


def upgrade():
    _set_role("DRIVER", DRIVER_DEPARTMENTS)
    _set_role("HELPER", HELPER_DEPARTMENTS)


def downgrade():
    # A data fix: which accounts were Employee before isn't kept, and
    # Driver / Helper is the right role for them anyway.
    pass
