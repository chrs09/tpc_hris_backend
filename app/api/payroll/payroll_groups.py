# app/api/payroll/payroll_groups.py
#
# Payroll Groups: departments paid by the same rule and cutoff, run as one
# payroll (see app/models/payroll_group.py). The group's cutoff is set
# through /payroll-cutoffs/{group name} like before.

import json
from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.employees import Employee
from app.models.payroll_cutoff_rule import PayrollCutoffRule
from app.models.payroll_deductions import PayrollDeduction
from app.models.payroll_group import PayrollGroup
from app.models.payroll_run import PayrollRun
from app.models.payslip_release import PayslipRelease
from app.models.user import User
from app.services.payroll_groups import (
    PAY_BASES,
    PAYROLL_TYPES,
    active_groups,
    departments_of,
    group_for,
    normalize_payroll_type,
)

router = APIRouter(prefix="/payroll-groups", tags=["Payroll Groups"])

# Reading: the Payroll page needs the groups. Changing: Payroll Cutoffs.
_require_read = require_role_or_module(
    roles=["admin", "payroll_admin"],
    module_key=["payroll.payroll", "payroll.payroll_cutoffs"],
)
_require_edit = require_role_or_module(
    roles=["admin", "payroll_admin"], module_key="payroll.payroll_cutoffs"
)


class GroupIn(BaseModel):
    name: str
    pay_basis: str
    departments: list[str]
    payroll_type: str | None = None
    sort_order: int | None = None


def _serialize(group: PayrollGroup) -> dict:
    return {
        "id": group.id,
        "name": group.name,
        "pay_basis": group.pay_basis,
        "departments": departments_of(group),
        "payroll_type": group.payroll_type,
        "sort_order": group.sort_order,
        "is_active": group.is_active,
    }


def _employee_departments(db: Session) -> list[tuple[str, str]]:
    """(department, Monthly/Daily) of every active employee."""
    return [
        (dept, normalize_payroll_type(ptype))
        for dept, ptype in db.query(Employee.department, Employee.payroll_type)
        .filter(Employee.is_active == 1, Employee.department.isnot(None))
        .all()
        if dept
    ]


@router.get("")
def list_payroll_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_read),
):
    """The groups, how many active employees each has, and anyone whose
    department / payroll type isn't in a group yet."""
    groups = active_groups(db)
    counts: Counter = Counter()
    unassigned: Counter = Counter()
    for dept, ptype in _employee_departments(db):
        group = group_for(groups, dept, ptype)
        if group:
            counts[group.id] += 1
        else:
            unassigned[(dept, ptype)] += 1
    return {
        "groups": [{**_serialize(g), "employee_count": counts[g.id]} for g in groups],
        "departments": sorted({dept for dept, _ in _employee_departments(db)}),
        "unassigned": [
            {"department": dept, "payroll_type": ptype, "employees": n}
            for (dept, ptype), n in sorted(unassigned.items())
        ],
    }


def _validate(db: Session, payload: GroupIn, group_id: int | None) -> dict:
    name = payload.name.strip()
    if not name or len(name) > 50:
        raise HTTPException(status_code=400, detail="Group name is required (up to 50 characters).")
    if payload.pay_basis not in PAY_BASES:
        raise HTTPException(status_code=400, detail="Pick how the group is paid.")
    ptype = payload.payroll_type or None
    if ptype and ptype not in PAYROLL_TYPES:
        raise HTTPException(status_code=400, detail="Payroll type must be Monthly or Daily.")
    departments = sorted({d.strip() for d in payload.departments if d and d.strip()})
    if not departments:
        raise HTTPException(status_code=400, detail="Pick at least one department.")

    lower = name.lower()
    taken = (
        db.query(PayrollGroup.id)
        .filter(PayrollGroup.name == name, PayrollGroup.id != (group_id or 0))
        .first()
    )
    if taken:
        raise HTTPException(status_code=400, detail="Another group already has this name.")
    # Payrolls from before groups are stored under department names.
    if lower in {d.lower() for d, _ in _employee_departments(db)}:
        raise HTTPException(
            status_code=400, detail="A group can't have the same name as a department."
        )

    # A department + payroll type can be in only one group.
    for other in active_groups(db):
        if other.id == group_id:
            continue
        overlap = {d.lower() for d in departments_of(other)} & {d.lower() for d in departments}
        if overlap and (not ptype or not other.payroll_type or ptype == other.payroll_type):
            raise HTTPException(
                status_code=400,
                detail=f"{', '.join(sorted(overlap))} is already in {other.name}.",
            )
    return {"name": name, "pay_basis": payload.pay_basis, "payroll_type": ptype, "departments": departments}


@router.post("")
def create_payroll_group(
    payload: GroupIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_edit),
):
    values = _validate(db, payload, None)
    group = PayrollGroup(
        name=values["name"],
        pay_basis=values["pay_basis"],
        payroll_type=values["payroll_type"],
        departments=json.dumps(values["departments"]),
        sort_order=payload.sort_order or (len(active_groups(db)) + 1),
        updated_by_user_id=current_user.id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return _serialize(group)


@router.patch("/{group_id}")
def update_payroll_group(
    group_id: int,
    payload: GroupIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_edit),
):
    group = db.query(PayrollGroup).filter(PayrollGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Payroll group not found.")
    values = _validate(db, payload, group_id)

    old_name = group.name
    if values["name"] != old_name:
        # Its cutoff, payroll statuses, saved figures and released
        # payslips follow the name.
        for model in (PayrollCutoffRule, PayrollRun, PayrollDeduction, PayslipRelease):
            db.query(model).filter(model.department == old_name).update(
                {model.department: values["name"]}, synchronize_session=False
            )
    group.name = values["name"]
    group.pay_basis = values["pay_basis"]
    group.payroll_type = values["payroll_type"]
    group.departments = json.dumps(values["departments"])
    if payload.sort_order is not None:
        group.sort_order = payload.sort_order
    group.updated_by_user_id = current_user.id
    group.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(group)
    return _serialize(group)


@router.delete("/{group_id}")
def delete_payroll_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_edit),
):
    group = db.query(PayrollGroup).filter(PayrollGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Payroll group not found.")
    has_payroll = (
        db.query(PayrollRun.id).filter(PayrollRun.department == group.name).first()
    )
    if has_payroll:
        raise HTTPException(
            status_code=400,
            detail="This group already has payrolls, so it can't be deleted. Move its departments to another group instead.",
        )
    db.query(PayrollCutoffRule).filter(PayrollCutoffRule.department == group.name).delete(
        synchronize_session=False
    )
    db.delete(group)
    db.commit()
    return {"message": "Payroll group deleted."}
