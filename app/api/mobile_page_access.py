from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_superadmin
from app.models.user import User
from app.models.employees import Employee
from app.models.department_head import DepartmentHead
from app.models.mobile_page_access import MobilePageAccess
from app.schemas.mobile_page_access import MobilePageAccessSet

router = APIRouter(prefix="/mobile-page-access", tags=["Mobile Page Access"])

# Canonical set of mobile pages that can be individually granted/denied,
# and the role defaults each one falls back to when an employee has no
# custom mobile grants configured (has_custom_mobile_access False) --
# these defaults mirror the hardcoded role arrays already used in the
# mobile app's employee/_layout.tsx and trips.tsx before this endpoint
# existed. Only covers pages actually built in the mobile app so far --
# Home/Leave/Overtime (filing) stay always-visible self-service and are
# deliberately not included here.
MOBILE_PAGES = {
    "trip_monitor": {
        "label": "Trips - Monitor",
        "default_roles": ["coordinator", "coordinator_admin", "admin", "superadmin"],
    },
    "trip_assign": {
        "label": "Trips - Assign Trip",
        "default_roles": ["coordinator", "coordinator_admin", "admin", "superadmin"],
    },
    "trip_approvals": {
        "label": "Trips - Trip Approvals",
        "default_roles": ["coordinator_admin", "admin", "superadmin"],
    },
    "trip_review": {
        "label": "Trip Review (Office)",
        "default_roles": ["office_admin", "coordinator_admin", "admin", "superadmin"],
    },
    # No default_roles -- OT Approvals' role default isn't a fixed role
    # list, it's "is this employee set as a department head" (see
    # is_department_head below), computed dynamically instead.
    "ot_approvals": {
        "label": "OT Approvals",
        "default_roles": [],
    },
}

ALL_PAGE_KEYS = set(MOBILE_PAGES.keys())


def is_department_head(user_id: int, db: Session) -> bool:
    return (
        db.query(DepartmentHead)
        .filter(DepartmentHead.head_user_id == user_id)
        .first()
        is not None
    )


@router.get("/pages")
def get_mobile_pages(current_user: User = Depends(require_superadmin)):
    return [
        {"key": key, "label": info["label"]} for key, info in MOBILE_PAGES.items()
    ]


@router.get("/employees")
def list_employees_with_mobile_access(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    employees = (
        db.query(Employee)
        .filter(Employee.is_active == 1)
        .order_by(Employee.last_name.asc())
        .all()
    )

    employee_ids = [e.id for e in employees]
    grants_by_employee: dict[int, list[str]] = {}
    if employee_ids:
        rows = (
            db.query(MobilePageAccess)
            .filter(MobilePageAccess.employee_id.in_(employee_ids))
            .all()
        )
        for row in rows:
            grants_by_employee.setdefault(row.employee_id, []).append(row.page_key)

    return [
        {
            "id": emp.id,
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "department": emp.department,
            "position": emp.position,
            "page_keys": grants_by_employee.get(emp.id, []),
            "has_custom_access": emp.has_custom_mobile_access,
        }
        for emp in employees
    ]


@router.put("/{employee_id}")
def set_employee_mobile_access(
    employee_id: int,
    payload: MobilePageAccessSet,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found.")

    invalid = [k for k in payload.page_keys if k not in ALL_PAGE_KEYS]
    if invalid:
        raise HTTPException(
            status_code=400, detail=f"Unknown page key(s): {', '.join(invalid)}"
        )

    db.query(MobilePageAccess).filter(
        MobilePageAccess.employee_id == employee_id
    ).delete()

    for key in set(payload.page_keys):
        db.add(
            MobilePageAccess(
                employee_id=employee_id,
                page_key=key,
                granted_by_user_id=current_user.id,
            )
        )

    employee.has_custom_mobile_access = True
    db.commit()

    return {
        "employee_id": employee_id,
        "page_keys": sorted(set(payload.page_keys)),
        "has_custom_access": True,
    }


@router.delete("/{employee_id}")
def reset_employee_mobile_access(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found.")

    db.query(MobilePageAccess).filter(
        MobilePageAccess.employee_id == employee_id
    ).delete()
    employee.has_custom_mobile_access = False
    db.commit()

    return {"employee_id": employee_id, "page_keys": [], "has_custom_access": False}


@router.get("/mine")
def get_my_mobile_access(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """What the logged-in mobile user should see. `is_approver` is always
    computed live (a superadmin grant of "ot_approvals" still requires
    the OT endpoints' own eligibility check to actually approve anything
    -- this flag only decides whether to show the tab when the employee
    has no custom mobile grants configured)."""
    role_value = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else current_user.role
    )

    employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
        if current_user.employee_id
        else None
    )

    is_approver = is_department_head(current_user.id, db)

    if not employee:
        return {
            "page_keys": [],
            "has_custom_access": False,
            "is_approver": is_approver,
            "role": role_value,
        }

    rows = (
        db.query(MobilePageAccess)
        .filter(MobilePageAccess.employee_id == employee.id)
        .all()
    )

    return {
        "page_keys": [r.page_key for r in rows],
        "has_custom_access": employee.has_custom_mobile_access,
        "is_approver": is_approver,
        "role": role_value,
    }
