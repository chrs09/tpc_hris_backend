# app/api/org_chart.py
#
# Organizational chart (Administrator -> Org Chart): a tree of units
# (Owner -> Admins -> HR / IT / Trip Management -> Coordinator ->
# Drivers ...). Members are resolved live from each unit's rules
# (positions, user roles, departments, pinned employees) -- see
# app/models/org_unit.py. Viewing: superadmin or the Hierarchy module.
# Changing the structure: superadmin only. What a person can access is
# saved through Module Assignment (app/api/employee_module_access.py).

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import require_role_or_module, require_superadmin
from app.models.employee_module_access import EmployeeModuleAccess
from app.models.employees import Employee
from app.models.files import File as FileModel
from app.models.org_unit import OrgUnit
from app.models.user import User, UserRole

router = APIRouter(prefix="/org-chart", tags=["Org Chart"])

_require_view = require_role_or_module(roles=[], module_key="administrator.hierarchy")

COMPANY_NAME = "Tytan Prime Corporation"


def _load(value) -> list:
    try:
        data = json.loads(value) if value else []
        return data if isinstance(data, list) else []
    except (TypeError, ValueError):
        return []


def _role(user: User | None) -> str | None:
    if not user:
        return None
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return role.lower()


class UnitCreate(BaseModel):
    name: str
    parent_id: int | None = None


class UnitUpdate(BaseModel):
    name: str | None = None
    # Use -1 to move to the top level (no parent).
    parent_id: int | None = None
    # 0 clears the head.
    head_user_id: int | None = None
    # Extra units it also reports to (drawn once, linked from these).
    also_reports_to: list[int] | None = None
    sort_order: int | None = None
    positions: list[str] | None = None
    roles: list[str] | None = None
    departments: list[str] | None = None
    employee_ids: list[int] | None = None


@router.get("")
def get_org_chart(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    units = db.query(OrgUnit).order_by(OrgUnit.sort_order.asc(), OrgUnit.id.asc()).all()
    employees = (
        db.query(Employee)
        .filter(Employee.is_active == 1)
        .order_by(Employee.last_name.asc(), Employee.first_name.asc())
        .all()
    )
    users = db.query(User).options(joinedload(User.employee)).all()
    user_by_employee = {u.employee_id: u for u in users if u.employee_id}
    user_by_id = {u.id: u for u in users}

    grants: dict[int, list[str]] = {}
    read_only: dict[int, list[str]] = {}
    for row in db.query(EmployeeModuleAccess):
        grants.setdefault(row.employee_id, []).append(row.module_key)
        if not row.can_edit:
            read_only.setdefault(row.employee_id, []).append(row.module_key)

    # Profile pictures (same file the Employees page shows); newest wins.
    photos: dict[int, str] = {}
    for f in (
        db.query(FileModel)
        .filter(
            FileModel.entity_type == "employee",
            func.upper(FileModel.document_type) == "PROFILE_IMAGE",
        )
        .order_by(FileModel.id.asc())
    ):
        if f.file_url:
            photos[f.entity_id] = f.file_url

    def person_from_employee(emp: Employee) -> dict:
        user = user_by_employee.get(emp.id)
        return {
            "employee_id": emp.id,
            "user_id": user.id if user else None,
            "name": " ".join(f"{emp.first_name or ''} {emp.last_name or ''}".split()),
            "position": emp.position,
            "department": emp.department,
            "photo_url": photos.get(emp.id),
            "role": _role(user),
            "has_custom_access": bool(emp.has_custom_module_access),
            "module_keys": sorted(grants.get(emp.id, [])),
            "read_only_keys": sorted(read_only.get(emp.id, [])),
        }

    def person_from_user(user: User) -> dict:
        if user.employee:
            return person_from_employee(user.employee)
        return {
            "employee_id": None,
            "user_id": user.id,
            "name": user.username,
            "position": None,
            "department": None,
            "photo_url": None,
            "role": _role(user),
            "has_custom_access": False,
            "module_keys": [],
            "read_only_keys": [],
        }

    result = []
    for unit in units:
        positions = {p.strip().lower() for p in _load(unit.member_positions)}
        roles = {r.strip().lower() for r in _load(unit.member_roles)}
        departments = set(_load(unit.member_departments))
        pinned = {int(i) for i in _load(unit.member_employee_ids)}

        members = []
        for emp in employees:
            user = user_by_employee.get(emp.id)
            if (
                emp.id in pinned
                or ((emp.position or "").strip().lower() in positions)
                or (emp.department in departments)
                or (user is not None and _role(user) in roles)
            ):
                members.append(person_from_employee(emp))
        # Users with a matching role but no employee record (e.g. a
        # superadmin login) still belong to the unit.
        for user in users:
            if not user.employee_id and user.is_active and _role(user) in roles:
                members.append(person_from_user(user))

        head_user = user_by_id.get(unit.head_user_id) if unit.head_user_id else None
        result.append(
            {
                "id": unit.id,
                "name": unit.name,
                "parent_id": unit.parent_id,
                "also_reports_to": [
                    int(i) for i in _load(unit.also_reports_to) if int(i) != unit.id
                ],
                "sort_order": unit.sort_order,
                "head": person_from_user(head_user) if head_user else None,
                "rules": {
                    "positions": _load(unit.member_positions),
                    "roles": _load(unit.member_roles),
                    "departments": _load(unit.member_departments),
                    "employee_ids": [int(i) for i in _load(unit.member_employee_ids)],
                },
                "members": members,
            }
        )

    return {
        "company": COMPANY_NAME,
        "employee_count": len(employees),
        "units": result,
        # Choices for the member-rule pickers.
        "options": {
            "positions": sorted({e.position for e in employees if e.position}),
            "departments": sorted({e.department for e in employees if e.department}),
            "roles": [r.value for r in UserRole],
            "employees": [
                {
                    "id": e.id,
                    "label": " ".join(f"{e.first_name or ''} {e.last_name or ''}".split())
                    + (f" ({e.position})" if e.position else ""),
                }
                for e in employees
            ],
        },
    }


def _get_unit(db: Session, unit_id: int) -> OrgUnit:
    unit = db.query(OrgUnit).filter(OrgUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found.")
    return unit


def _clean_name(name: str | None) -> str:
    name = " ".join((name or "").split())
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Name is too long.")
    return name


@router.post("/units")
def create_unit(
    payload: UnitCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    if payload.parent_id is not None:
        _get_unit(db, payload.parent_id)
    siblings = db.query(OrgUnit).filter(OrgUnit.parent_id == payload.parent_id).count()
    unit = OrgUnit(
        name=_clean_name(payload.name),
        parent_id=payload.parent_id,
        sort_order=siblings,
        member_positions="[]",
        member_roles="[]",
        member_departments="[]",
        member_employee_ids="[]",
        updated_by_user_id=current_user.id,
    )
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return {"id": unit.id, "message": "Unit added."}


@router.put("/units/{unit_id}")
def update_unit(
    unit_id: int,
    payload: UnitUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    unit = _get_unit(db, unit_id)

    if payload.name is not None:
        unit.name = _clean_name(payload.name)

    if payload.parent_id is not None:
        new_parent = None if payload.parent_id == -1 else payload.parent_id
        if new_parent is not None:
            # Can't move a unit under itself or its own descendant.
            cursor = _get_unit(db, new_parent)
            while cursor is not None:
                if cursor.id == unit.id:
                    raise HTTPException(
                        status_code=400,
                        detail="A unit can't be moved under itself or one of its own units.",
                    )
                cursor = (
                    db.query(OrgUnit).filter(OrgUnit.id == cursor.parent_id).first()
                    if cursor.parent_id
                    else None
                )
        unit.parent_id = new_parent

    if payload.also_reports_to is not None:
        extra = sorted(
            {i for i in payload.also_reports_to if i != unit.id and i != unit.parent_id}
        )
        found = {u.id for u in db.query(OrgUnit.id).filter(OrgUnit.id.in_(extra or [0]))}
        missing = [i for i in extra if i not in found]
        if missing:
            raise HTTPException(status_code=400, detail="Unit not found.")
        unit.also_reports_to = json.dumps(extra)

    if payload.head_user_id is not None:
        if payload.head_user_id == 0:
            unit.head_user_id = None
        else:
            if not db.query(User.id).filter(User.id == payload.head_user_id).first():
                raise HTTPException(status_code=400, detail="Head not found.")
            unit.head_user_id = payload.head_user_id

    if payload.sort_order is not None:
        unit.sort_order = payload.sort_order

    valid_roles = {r.value for r in UserRole}
    if payload.roles is not None:
        bad = [r for r in payload.roles if r not in valid_roles]
        if bad:
            raise HTTPException(status_code=400, detail=f"Unknown role: {bad[0]}")
        unit.member_roles = json.dumps(sorted(set(payload.roles)))
    if payload.positions is not None:
        unit.member_positions = json.dumps(
            sorted({p.strip() for p in payload.positions if p.strip()})
        )
    if payload.departments is not None:
        unit.member_departments = json.dumps(
            sorted({d.strip() for d in payload.departments if d.strip()})
        )
    if payload.employee_ids is not None:
        unit.member_employee_ids = json.dumps(sorted(set(payload.employee_ids)))

    unit.updated_by_user_id = current_user.id
    db.commit()
    return {"message": "Unit updated."}


@router.delete("/units/{unit_id}")
def delete_unit(
    unit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Removes a unit; its sub-units move up to its parent (nothing else
    is deleted -- members are only matched by rules)."""
    unit = _get_unit(db, unit_id)
    for child in db.query(OrgUnit).filter(OrgUnit.parent_id == unit.id):
        child.parent_id = unit.parent_id
    # Drop it from other units' "also reports to" lists.
    for other in db.query(OrgUnit).filter(OrgUnit.also_reports_to.isnot(None)):
        ids = [int(i) for i in _load(other.also_reports_to)]
        if unit.id in ids:
            other.also_reports_to = json.dumps([i for i in ids if i != unit.id])
    db.flush()
    db.delete(unit)
    db.commit()
    return {"message": "Unit removed."}
