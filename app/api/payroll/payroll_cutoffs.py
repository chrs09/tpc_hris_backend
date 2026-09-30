# app/api/payroll/payroll_cutoffs.py
#
# Payroll Cutoffs: how each department (employee group) is paid --
# semi-monthly, weekly or monthly -- read by the Payroll page to build
# its cutoff periods. See app/models/payroll_cutoff_rule.py for what each
# field means.

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.employees import Employee
from app.models.payroll_cutoff_rule import PayrollCutoffRule
from app.models.user import User

router = APIRouter(prefix="/payroll-cutoffs", tags=["Payroll Cutoffs"])

# Same access as the Payroll page; "Can edit: No" makes it view-only.
_require_payroll = require_role_or_module(
    roles=["admin", "payroll_admin"], module_key="payroll.payroll"
)

SCHEDULE_TYPES = ("semi_monthly", "weekly", "monthly")


class CutoffRuleIn(BaseModel):
    schedule_type: str
    first_start_day: int | None = None
    second_start_day: int | None = None
    first_payout_day: int | None = None
    second_payout_day: int | None = None
    week_start_day: int | None = None
    payout_offset_days: int | None = None


def _serialize(rule: PayrollCutoffRule) -> dict:
    return {
        "department": rule.department,
        "schedule_type": rule.schedule_type,
        "first_start_day": rule.first_start_day,
        "second_start_day": rule.second_start_day,
        "first_payout_day": rule.first_payout_day,
        "second_payout_day": rule.second_payout_day,
        "week_start_day": rule.week_start_day,
        "payout_offset_days": rule.payout_offset_days,
        "updated_at": rule.updated_at,
    }


def _payout_day(value, label):
    if value is None or not (0 <= value <= 31):
        raise HTTPException(
            status_code=400, detail=f"{label} must be 1-31, or 0 for month end."
        )
    return value


@router.get("")
def list_cutoff_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    """Every rule, plus the departments employees are in -- so the page
    can show groups that still have no cutoff set."""
    rules = db.query(PayrollCutoffRule).order_by(PayrollCutoffRule.department).all()
    departments = sorted(
        {
            row[0]
            for row in db.query(Employee.department)
            .filter(Employee.is_active == 1, Employee.department.isnot(None))
            .all()
            if row[0]
        }
    )
    return {"rules": [_serialize(r) for r in rules], "departments": departments}


@router.put("/{department}")
def save_cutoff_rule(
    department: str,
    payload: CutoffRuleIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    department = department.strip()
    if not department or len(department) > 50:
        raise HTTPException(status_code=400, detail="Invalid department.")
    if payload.schedule_type not in SCHEDULE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid schedule type.")

    values = {
        "first_start_day": None,
        "second_start_day": None,
        "first_payout_day": None,
        "second_payout_day": None,
        "week_start_day": None,
        "payout_offset_days": None,
    }
    if payload.schedule_type == "semi_monthly":
        s1, s2 = payload.first_start_day, payload.second_start_day
        if s1 is None or s2 is None or not (1 <= s1 < s2 <= 28):
            raise HTTPException(
                status_code=400,
                detail="Cutoff start days must be between 1 and 28, first before second.",
            )
        values.update(
            first_start_day=s1,
            second_start_day=s2,
            first_payout_day=_payout_day(payload.first_payout_day, "First payout day"),
            second_payout_day=_payout_day(payload.second_payout_day, "Second payout day"),
        )
    elif payload.schedule_type == "weekly":
        ws, off = payload.week_start_day, payload.payout_offset_days
        if ws is None or not (0 <= ws <= 6):
            raise HTTPException(status_code=400, detail="Pick the day the week starts.")
        if off is None or not (0 <= off <= 14):
            raise HTTPException(
                status_code=400, detail="Payout must be 0-14 days after the cutoff."
            )
        values.update(week_start_day=ws, payout_offset_days=off)
    else:
        values.update(
            first_payout_day=_payout_day(payload.first_payout_day, "Payout day")
        )

    rule = (
        db.query(PayrollCutoffRule)
        .filter(PayrollCutoffRule.department == department)
        .first()
    )
    if not rule:
        rule = PayrollCutoffRule(department=department)
        db.add(rule)
    rule.schedule_type = payload.schedule_type
    for key, value in values.items():
        setattr(rule, key, value)
    rule.updated_by_user_id = current_user.id
    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)
    return _serialize(rule)


@router.delete("/{department}")
def delete_cutoff_rule(
    department: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    rule = (
        db.query(PayrollCutoffRule)
        .filter(PayrollCutoffRule.department == department)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="No cutoff set for that department.")
    db.delete(rule)
    db.commit()
    return {"message": "Cutoff removed."}
