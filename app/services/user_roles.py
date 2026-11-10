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



def driver_user_condition():
    """SQLAlchemy filter for users who can be a trip's driver: the Driver
    role, or a relief driver -- any active helper (rare, so no per-person
    setting; dispatch's "Helper as Driver" checkbox lists them). Use with
    db.query(User).filter(...)."""
    from sqlalchemy import func, or_, select

    from app.models.employees import Employee
    from app.models.user import User

    return or_(
        User.role == UserRole.DRIVER,
        User.employee_id.in_(
            select(Employee.id).where(
                func.upper(Employee.position) == "HELPER", Employee.is_active == 1
            )
        ),
    )


def is_relief_driver(user) -> bool:
    """A helper (not the Driver role) picked to drive."""
    role = getattr(user.role, "value", user.role)
    employee = getattr(user, "employee", None)
    return (
        role != UserRole.DRIVER.value
        and employee is not None
        and (employee.position or "").upper() == "HELPER"
    )

def check_trip_crew(db, driver, helper_ids, trip_id=None, keep_helper_ids=()):
    """Relief-driver rules for a trip's crew (raises HTTPException 400):
    - one person, one slot: the driver can't also be a helper;
    - a relief driver out on another trip as a helper isn't free to drive;
    - a helper driving another trip (assigned / in progress) isn't free.
    `trip_id` = the trip being edited (its own crew doesn't count as busy);
    `keep_helper_ids` = helpers already on it."""
    from fastapi import HTTPException

    from app.models.trips import Trip, TripStatus
    from app.models.user import User

    helper_ids = [int(h) for h in helper_ids]
    if driver.employee_id and driver.employee_id in helper_ids:
        raise HTTPException(
            status_code=400,
            detail="The driver can't also be a helper on the same trip.",
        )

    employee = getattr(driver, "employee", None)
    if (
        is_relief_driver(driver)
        and employee is not None
        and not employee.is_available
        and driver.employee_id not in keep_helper_ids
    ):
        raise HTTPException(
            status_code=400,
            detail=f"{employee.first_name} is out on another trip as a helper.",
        )

    new_helpers = [h for h in helper_ids if h not in keep_helper_ids]
    if not new_helpers:
        return
    driving = (
        db.query(User.employee_id)
        .join(Trip, Trip.driver_id == User.id)
        .filter(
            User.employee_id.in_(new_helpers),
            Trip.status.in_([TripStatus.ASSIGNED, TripStatus.ACTIVE]),
            *([Trip.id != trip_id] if trip_id else []),
        )
        .first()
    )
    if driving:
        raise HTTPException(
            status_code=400,
            detail="A selected helper is driving another trip right now.",
        )
