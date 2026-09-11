from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_superadmin, get_current_user
from app.models.user import User
from app.models.employees import Employee
from app.models.employee_module_access import EmployeeModuleAccess
from app.schemas.employee_module_access import ModuleAccessSet

router = APIRouter(prefix="/employee-module-access", tags=["Employee Module Access"])

# Canonical assignable module/submodule structure. Keys must match
# MODULE_GROUPS in tpc_hris_frontend/src/constants/modules.js -- the
# Sidebar checks these same keys against an employee's granted set instead
# of the old hardcoded role arrays. "Dashboard" and "Administrator" are
# intentionally excluded -- those stay as they are today (always visible /
# superadmin-only), not part of the assignable set.
MODULE_GROUPS = {
    "hris": [
        "attendance",
        "leave",
        "employees",
        "applicants",
        "questionnaire",
    ],
    "payroll": ["payroll"],
    "trip_management": [
        "trips",
        "office_trip_review",
        "trip_bypass",
        "trip_categories",
        "daily_dispatch",
    ],
    "customers": ["customers"],
    "suppliers": ["suppliers"],
    "fleet_management": ["vehicle_list", "vehicle_maintenance"],
    "finance": ["finance_trips", "finance_expenses"],
}

ALL_MODULE_KEYS = {
    f"{group}.{sub}" for group, subs in MODULE_GROUPS.items() for sub in subs
}

DEPARTMENT_ORDER = [
    "Admin",
    "Yard",
    "Motorpool",
    "Dumptruck",
    "Labor",
    "CdcDriver",
    "CdcHelper",
    "CpdcDriver",
    "CpdcHelper",
    "WingvanDriver",
]


@router.get("/modules")
def get_module_definitions(current_user: User = Depends(require_superadmin)):
    return MODULE_GROUPS


@router.get("/employees")
def list_employees_with_access(
    department: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    query = db.query(Employee).filter(Employee.is_active == 1)
    if department:
        query = query.filter(Employee.department == department)

    order = case(
        {dept: i for i, dept in enumerate(DEPARTMENT_ORDER)},
        value=Employee.department,
        else_=len(DEPARTMENT_ORDER),
    )
    employees = query.order_by(order, Employee.last_name.asc()).all()

    employee_ids = [e.id for e in employees]
    grants_by_employee: dict[int, list[str]] = {}
    if employee_ids:
        rows = (
            db.query(EmployeeModuleAccess)
            .filter(EmployeeModuleAccess.employee_id.in_(employee_ids))
            .all()
        )
        for row in rows:
            grants_by_employee.setdefault(row.employee_id, []).append(row.module_key)

    return [
        {
            "id": emp.id,
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "department": emp.department,
            "position": emp.position,
            "module_keys": grants_by_employee.get(emp.id, []),
            "has_custom_access": emp.has_custom_module_access,
        }
        for emp in employees
    ]


@router.put("/{employee_id}")
def set_employee_module_access(
    employee_id: int,
    payload: ModuleAccessSet,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found.")

    invalid = [k for k in payload.module_keys if k not in ALL_MODULE_KEYS]
    if invalid:
        raise HTTPException(
            status_code=400, detail=f"Unknown module key(s): {', '.join(invalid)}"
        )

    # Full replace -- simplest semantics for a checkbox grid saved per row.
    db.query(EmployeeModuleAccess).filter(
        EmployeeModuleAccess.employee_id == employee_id
    ).delete()

    for key in set(payload.module_keys):
        db.add(
            EmployeeModuleAccess(
                employee_id=employee_id,
                module_key=key,
                granted_by_user_id=current_user.id,
            )
        )

    # Marks this employee as customized -- from now on the Sidebar uses
    # ONLY these granted keys for the assignable groups, ignoring their
    # role, even if the set saved here is empty (deliberately locking them
    # out rather than falling back to role defaults).
    employee.has_custom_module_access = True

    db.commit()

    return {
        "employee_id": employee_id,
        "module_keys": sorted(set(payload.module_keys)),
        "has_custom_access": True,
    }


@router.delete("/{employee_id}")
def reset_employee_module_access(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Clears an employee's custom module access entirely and reverts them
    to their role's default access -- undoes set_employee_module_access."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found.")

    db.query(EmployeeModuleAccess).filter(
        EmployeeModuleAccess.employee_id == employee_id
    ).delete()
    employee.has_custom_module_access = False

    db.commit()

    return {"employee_id": employee_id, "module_keys": [], "has_custom_access": False}


@router.get("/mine")
def get_my_module_access(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Which submodules the logged-in user's own employee record has been
    granted -- consumed by the frontend Sidebar to decide what to show for
    non-superadmin roles.

    has_custom_access distinguishes "superadmin has never configured this
    employee, use their role's default access" (False) from "superadmin
    has explicitly set this employee's access -- use ONLY module_keys,
    even if it's empty" (True). Without that flag, an employee explicitly
    locked out of everything would be indistinguishable from one who was
    simply never configured, and would incorrectly fall back to their
    role's full default access."""
    employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
        if current_user.employee_id
        else None
    )
    if not employee:
        return {"module_keys": [], "has_custom_access": False}

    rows = (
        db.query(EmployeeModuleAccess)
        .filter(EmployeeModuleAccess.employee_id == employee.id)
        .all()
    )
    return {
        "module_keys": [r.module_key for r in rows],
        "has_custom_access": employee.has_custom_module_access,
    }
