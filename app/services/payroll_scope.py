"""Which payroll groups a person may work on (Org Chart -> What they can
access -> Payroll -> payroll groups). Stored on their "payroll.payroll"
grant (EmployeeModuleAccess.payroll_groups); empty = every group.

Superadmin, the payroll roles without custom access, and grants with no
groups picked see everything (None). Otherwise only those groups'
payrolls, and only their employees' pay / attendance / overtime /
incentive data on the Payroll page.
"""

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.employee_module_access import EmployeeModuleAccess
from app.models.employees import Employee
from app.models.user import User
from app.services.payroll_groups import active_groups, group_for

PAYROLL_MODULE = "payroll.payroll"


def load_groups(value) -> list[str]:
    try:
        groups = json.loads(value or "[]")
    except ValueError:
        return []
    return [str(g) for g in groups if g]


def allowed_payroll_groups(db: Session, user: User | None) -> set[str] | None:
    """The payroll group names this person is limited to, or None (all)."""
    if user is None or not user.employee_id:
        return None
    role = user.role.value if hasattr(user.role, "value") else user.role
    if role == "superadmin":
        return None
    row = (
        db.query(EmployeeModuleAccess.payroll_groups)
        .join(Employee, Employee.id == EmployeeModuleAccess.employee_id)
        .filter(
            Employee.id == user.employee_id,
            Employee.has_custom_module_access.is_(True),
            EmployeeModuleAccess.module_key == PAYROLL_MODULE,
        )
        .first()
    )
    groups = load_groups(row[0]) if row else []
    return set(groups) or None


def ensure_payroll_allowed(db: Session, user: User | None, payroll: str | None) -> None:
    """403 when `payroll` (a group, or a department from before groups) is
    outside the person's payroll groups."""
    allowed = allowed_payroll_groups(db, user)
    if allowed is not None and payroll not in allowed:
        raise HTTPException(
            status_code=403, detail="You don't have access to this payroll group."
        )


def allowed_employee_ids(db: Session, user: User | None) -> set[int] | None:
    """Employees in the person's payroll groups (by their department and
    payroll type today), or None (everyone)."""
    allowed = allowed_payroll_groups(db, user)
    if allowed is None:
        return None
    groups = active_groups(db)
    return {
        emp_id
        for emp_id, dept, ptype in db.query(
            Employee.id, Employee.department, Employee.payroll_type
        )
        if (group := group_for(groups, dept, ptype)) is not None and group.name in allowed
    }


def ensure_employee_allowed(db: Session, user: User | None, employee_id) -> None:
    ids = allowed_employee_ids(db, user)
    if ids is not None and int(employee_id or 0) not in ids:
        raise HTTPException(
            status_code=403, detail="This employee isn't in your payroll groups."
        )
