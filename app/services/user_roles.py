"""The login role a new account gets from the employee's department:
driver / helper departments get the Driver / Helper role (their app is
the trip workflow), everyone else Employee. Used by convert-to-employee
and Bulk Create Accounts; the web Create User form preselects the same
(tpc_hris_frontend/src/components/users/UserDrawer.jsx)."""

from app.models.user import UserRole

DRIVER_DEPARTMENTS = {"cdcdriver", "cpdcdriver", "wingvandriver"}
HELPER_DEPARTMENTS = {"cdchelper", "cpdchelper"}


def role_for_department(department: str | None) -> UserRole:
    dept = (department or "").strip().lower()
    if dept in DRIVER_DEPARTMENTS:
        return UserRole.DRIVER
    if dept in HELPER_DEPARTMENTS:
        return UserRole.HELPER
    return UserRole.EMPLOYEE
