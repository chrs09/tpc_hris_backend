from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import require_superadmin
from app.models.user import User
from app.models.department_head import DepartmentHead
from app.models.cash_advance_head import CashAdvanceHead
from app.schemas.department_head import DepartmentHeadSet

router = APIRouter(prefix="/org-hierarchy", tags=["Org Hierarchy"])

# Canonical department list, matching employeeRoleConvert in
# tpc_hris_frontend/src/constants/employeeRole.js.
DEPARTMENTS = [
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


def _serialize_user(user: User | None) -> dict | None:
    if not user:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "employee_name": (
            f"{user.employee.first_name} {user.employee.last_name}"
            if user.employee
            else None
        ),
    }


@router.get("/")
def list_department_heads(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    heads_by_department = {
        h.department: h
        for h in db.query(DepartmentHead)
        .options(joinedload(DepartmentHead.head_user).joinedload(User.employee))
        .all()
    }

    return [
        {
            "department": department,
            "head": _serialize_user(
                heads_by_department[department].head_user
                if department in heads_by_department
                else None
            ),
            "updated_at": (
                heads_by_department[department].updated_at
                if department in heads_by_department
                else None
            ),
        }
        for department in DEPARTMENTS
    ]


@router.put("/{department}")
def set_department_head(
    department: str,
    payload: DepartmentHeadSet,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    if department not in DEPARTMENTS:
        raise HTTPException(status_code=400, detail="Unknown department.")

    head_user = db.query(User).filter(User.id == payload.head_user_id).first()
    if not head_user:
        raise HTTPException(status_code=404, detail="Selected user not found.")

    entry = (
        db.query(DepartmentHead)
        .filter(DepartmentHead.department == department)
        .first()
    )

    if entry:
        entry.head_user_id = head_user.id
        entry.updated_by_user_id = current_user.id
    else:
        entry = DepartmentHead(
            department=department,
            head_user_id=head_user.id,
            updated_by_user_id=current_user.id,
        )
        db.add(entry)

    db.commit()
    db.refresh(entry)

    return {
        "department": entry.department,
        "head": _serialize_user(head_user),
        "updated_at": entry.updated_at,
    }


# =========================
# CASH ADVANCE IMMEDIATE HEAD
#
# A separate per-department assignment from the general DepartmentHead
# above -- lets a department route cash advance approvals to a different
# person than whoever approves overtime. Unset departments fall back to
# a superadmin at filing time (see file_cash_advance_request() in
# app/api/cash_advance_request.py) rather than blocking the request.
# =========================


@router.get("/cash-advance-heads")
def list_cash_advance_heads(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    heads_by_department = {
        h.department: h
        for h in db.query(CashAdvanceHead)
        .options(joinedload(CashAdvanceHead.head_user).joinedload(User.employee))
        .all()
    }

    return [
        {
            "department": department,
            "head": _serialize_user(
                heads_by_department[department].head_user
                if department in heads_by_department
                else None
            ),
            "updated_at": (
                heads_by_department[department].updated_at
                if department in heads_by_department
                else None
            ),
        }
        for department in DEPARTMENTS
    ]


@router.put("/cash-advance-heads/{department}")
def set_cash_advance_head(
    department: str,
    payload: DepartmentHeadSet,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    if department not in DEPARTMENTS:
        raise HTTPException(status_code=400, detail="Unknown department.")

    head_user = db.query(User).filter(User.id == payload.head_user_id).first()
    if not head_user:
        raise HTTPException(status_code=404, detail="Selected user not found.")

    entry = (
        db.query(CashAdvanceHead)
        .filter(CashAdvanceHead.department == department)
        .first()
    )

    if entry:
        entry.head_user_id = head_user.id
        entry.updated_by_user_id = current_user.id
    else:
        entry = CashAdvanceHead(
            department=department,
            head_user_id=head_user.id,
            updated_by_user_id=current_user.id,
        )
        db.add(entry)

    db.commit()
    db.refresh(entry)

    return {
        "department": entry.department,
        "head": _serialize_user(head_user),
        "updated_at": entry.updated_at,
    }
