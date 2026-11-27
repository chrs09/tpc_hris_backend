# app/api/gov_contributions.py
#
# HRIS -> Government Contributions: every employee with their SSS /
# PhilHealth / Pag-IBIG / TIN numbers (same fields as Employee Details ->
# Government & Legal) and which contributions payroll deducts for them.
# Payroll (PayrollList.jsx) reads the ticks from the employee list
# (`contributions`); unticked = not deducted.

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role_or_module
from app.models.employee_government import EmployeeGovernmentDetails
from app.models.employees import Employee
from app.models.user import User

router = APIRouter(prefix="/government-contributions", tags=["Government Contributions"])

_require_view = require_role_or_module(roles=["admin"], module_key="hris.government_contributions")

FLAGS = ("has_sss", "has_philhealth", "has_pagibig", "has_tax")
NUMBERS = ("sss_number", "philhealth_number", "pagibig_number", "tin_number")


def _row(emp: Employee, gov: EmployeeGovernmentDetails | None) -> dict:
    return {
        "employee_id": emp.id,
        "name": f"{emp.last_name}, {emp.first_name}" + (f" {emp.suffix}" if emp.suffix else ""),
        "department": emp.department,
        "position": emp.position,
        "payroll_type": emp.payroll_type,
        "is_active": bool(emp.is_active),
        **{n: (getattr(gov, n) if gov else None) for n in NUMBERS},
        **{f: bool(getattr(gov, f)) if gov else False for f in FLAGS},
    }


def _gov_for(db: Session, employee_id: int) -> EmployeeGovernmentDetails:
    gov = (
        db.query(EmployeeGovernmentDetails)
        .filter(EmployeeGovernmentDetails.employee_id == employee_id)
        .first()
    )
    if gov is None:
        gov = EmployeeGovernmentDetails(employee_id=employee_id)
        db.add(gov)
    return gov


@router.get("")
def list_contributions(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    query = db.query(Employee)
    if not include_inactive:
        query = query.filter(Employee.is_active == 1)
    employees = query.order_by(Employee.department, Employee.last_name, Employee.first_name).all()
    ids = [e.id for e in employees]
    govs = {
        g.employee_id: g
        for g in (
            db.query(EmployeeGovernmentDetails)
            .filter(EmployeeGovernmentDetails.employee_id.in_(ids))
            .all()
            if ids
            else []
        )
    }
    return [_row(e, govs.get(e.id)) for e in employees]


class ContributionIn(BaseModel):
    sss_number: str | None = None
    philhealth_number: str | None = None
    pagibig_number: str | None = None
    tin_number: str | None = None
    has_sss: bool | None = None
    has_philhealth: bool | None = None
    has_pagibig: bool | None = None
    has_tax: bool | None = None


def _ensure_can_edit(db: Session, user: User):
    from app.core.dependencies import has_editable_grant

    role = user.role.value if hasattr(user.role, "value") else user.role
    if role in ("superadmin", "admin") or has_editable_grant(
        db, user, ["hris.government_contributions"]
    ):
        return
    raise HTTPException(status_code=403, detail="You can view this page but not edit it.")


def _apply(gov: EmployeeGovernmentDetails, payload: ContributionIn):
    data = payload.model_dump(exclude_unset=True)
    for n in NUMBERS:
        if n in data:
            gov_value = (data[n] or "").strip()[:50] or None
            setattr(gov, n, gov_value)
    for f in FLAGS:
        if f in data and data[f] is not None:
            setattr(gov, f, bool(data[f]))


@router.put("/{employee_id}")
def update_contribution(
    employee_id: int,
    payload: ContributionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    _ensure_can_edit(db, current_user)
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found.")
    gov = _gov_for(db, employee_id)
    _apply(gov, payload)
    db.commit()
    db.refresh(gov)
    return _row(emp, gov)


class BulkIn(BaseModel):
    employee_ids: list[int]
    flag: str
    value: bool


@router.put("")
def bulk_update(
    payload: BulkIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    """Tick / untick one contribution for many employees (e.g. everyone
    shown on the page)."""
    _ensure_can_edit(db, current_user)
    if payload.flag not in FLAGS:
        raise HTTPException(status_code=400, detail="Unknown contribution.")
    ids = list(dict.fromkeys(payload.employee_ids))
    existing = {
        g.employee_id: g
        for g in db.query(EmployeeGovernmentDetails).filter(
            EmployeeGovernmentDetails.employee_id.in_(ids or [0])
        )
    }
    valid = {e_id for (e_id,) in db.query(Employee.id).filter(Employee.id.in_(ids or [0]))}
    for e_id in ids:
        if e_id not in valid:
            continue
        gov = existing.get(e_id)
        if gov is None:
            gov = EmployeeGovernmentDetails(employee_id=e_id)
            db.add(gov)
        setattr(gov, payload.flag, payload.value)
    db.commit()
    return {"updated": len(valid)}


# =========================================================
# SSS BASIS (what the SSS bracket is looked up from)
# =========================================================
# Per payroll type: "basic" = Base Pay (basic for the cutoff, no allowance /
# OT / holiday / others) or "gross" = Gross Pay. Payroll reads this.
SSS_BASIS_KEY = "sss_basis"
SSS_BASIS_TYPES = ("Monthly", "Daily", "Weekly")
SSS_BASIS_DEFAULT = {t: "basic" for t in SSS_BASIS_TYPES}


def sss_basis(db: Session) -> dict:
    import json

    from app.models.app_setting import AppSetting

    row = db.query(AppSetting).filter(AppSetting.key == SSS_BASIS_KEY).first()
    try:
        saved = json.loads(row.value) if row and row.value else {}
    except ValueError:
        saved = {}
    return {
        t: saved.get(t) if saved.get(t) in ("basic", "gross") else SSS_BASIS_DEFAULT[t]
        for t in SSS_BASIS_TYPES
    }


@router.get("/settings/sss-basis")
def get_sss_basis(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return sss_basis(db)


@router.put("/settings/sss-basis")
def set_sss_basis(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    import json

    from app.models.app_setting import AppSetting

    _ensure_can_edit(db, current_user)
    value = sss_basis(db)
    for t in SSS_BASIS_TYPES:
        if t in payload:
            if payload[t] not in ("basic", "gross"):
                raise HTTPException(status_code=400, detail="Pick Base Pay or Gross Pay.")
            value[t] = payload[t]
    row = db.query(AppSetting).filter(AppSetting.key == SSS_BASIS_KEY).first()
    if row is None:
        row = AppSetting(
            key=SSS_BASIS_KEY,
            value=json.dumps(value),
            description="SSS bracket basis per payroll type: basic (Base Pay) or gross (Gross Pay).",
        )
        db.add(row)
    else:
        row.value = json.dumps(value)
    db.commit()
    return value
