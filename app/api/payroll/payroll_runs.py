"""Payroll status per department + cutoff:

    DRAFT -> GENERATED -> FOR_REVIEW -> APPROVED -> LOCKED -> PAID

Who does each step is set per person on the Org Chart (Payroll ->
Prepare & Submit / Approve & Return / Lock & Mark Paid) -- the user's
role never grants these. Superadmin can always.

- Prepare & Submit: generate (repeatable until approved; re-generating
  recalculates the same payroll_deductions rows and sends a run under
  review back to GENERATED), edit figures, submit for review.
- Approve & Return: approve, or return for correction (with a reason).
- Lock & Mark Paid: lock the period, mark it paid.
- Unlock (back to APPROVED): superadmin only, with a reason.
"""

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role_or_module
from app.models.payroll_run import PayrollRun
from app.services.payroll_lock import (
    PAYROLL_APPROVE,
    PAYROLL_PREPARE,
    PAYROLL_RELEASE,
    can_payroll,
    ensure_can_payroll,
)
from app.models.user import User
from app.utils.user_display import display_name

router = APIRouter(prefix="/payroll-runs", tags=["Payroll Runs"])

_require_payroll = require_role_or_module(roles=["admin"], module_key="payroll.payroll")

EDITABLE_STATUSES = ("DRAFT", "GENERATED", "FOR_REVIEW")
STATUS_FLOW = ("DRAFT", "GENERATED", "FOR_REVIEW", "APPROVED", "LOCKED", "PAID")


def _role(user: User) -> str:
    return user.role.value if hasattr(user.role, "value") else user.role


def _period_dates(cutoff_period: str) -> tuple[date, date]:
    try:
        start, end = cutoff_period.split("_")
        return date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Cutoff period must look like 2026-10-01_2026-10-15."
        )


def _get_or_new(db: Session, department: str, cutoff_period: str) -> PayrollRun:
    run = (
        db.query(PayrollRun)
        .filter(PayrollRun.department == department, PayrollRun.cutoff_period == cutoff_period)
        .first()
    )
    if run:
        return run
    start, end = _period_dates(cutoff_period)
    run = PayrollRun(
        department=department,
        cutoff_period=cutoff_period,
        period_start=start,
        period_end=end,
        status="DRAFT",
        log="[]",
    )
    db.add(run)
    return run


def _log(db: Session, run: PayrollRun, action: str, user: User, note: str | None = None):
    entries = json.loads(run.log or "[]")
    entries.append(
        {
            "action": action,
            "status": run.status,
            "by": display_name(db.get(User, user.id)),
            "at": datetime.utcnow().isoformat(),
            "note": note,
        }
    )
    run.log = json.dumps(entries)


def _names(db: Session, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: display_name(u) for u in db.query(User).filter(User.id.in_(ids)).all()}


def _serialize(db: Session, run: PayrollRun | None, user: User, department: str, cutoff_period: str):
    can_prepare = can_payroll(db, user, PAYROLL_PREPARE)
    can_approve = can_payroll(db, user, PAYROLL_APPROVE)
    can_release = can_payroll(db, user, PAYROLL_RELEASE)
    is_superadmin = _role(user) == "superadmin"
    status = run.status if run else "DRAFT"
    names = _names(
        db,
        [
            run.generated_by, run.submitted_by, run.approved_by, run.locked_by, run.paid_by,
        ]
        if run
        else [],
    )

    def stamp(prefix):
        if not run or not getattr(run, f"{prefix}_at"):
            return None
        return {
            "at": getattr(run, f"{prefix}_at").isoformat(),
            "by": names.get(getattr(run, f"{prefix}_by")),
        }

    return {
        "department": department,
        "cutoff_period": cutoff_period,
        "status": status,
        "employee_count": run.employee_count if run else 0,
        "total_gross": float(run.total_gross or 0) if run else 0,
        "total_net": float(run.total_net or 0) if run else 0,
        "generated": stamp("generated"),
        "submitted": stamp("submitted"),
        "approved": stamp("approved"),
        "locked": stamp("locked"),
        "paid": stamp("paid"),
        "return_note": run.return_note if run else None,
        "log": json.loads(run.log or "[]") if run else [],
        # What this viewer may do next.
        # Generate + edit figures (deductions, OT) -- also gates the inputs.
        "can_generate": can_prepare and status in EDITABLE_STATUSES,
        "can_submit": can_prepare and status == "GENERATED",
        "can_approve": can_approve and status == "FOR_REVIEW",
        "can_return": can_approve and status in ("FOR_REVIEW", "APPROVED"),
        "can_lock": can_release and status == "APPROVED",
        "can_mark_paid": can_release and status == "LOCKED",
        "can_unlock": is_superadmin and status == "LOCKED",
        # This viewer's payroll steps, for the "waiting for ..." note.
        "my_steps": {
            "prepare": can_prepare,
            "approve": can_approve,
            "release": can_release,
        },
    }


@router.get("")
def get_payroll_run(
    department: str = Query(...),
    cutoff_period: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    run = (
        db.query(PayrollRun)
        .filter(PayrollRun.department == department, PayrollRun.cutoff_period == cutoff_period)
        .first()
    )
    return _serialize(db, run, current_user, department, cutoff_period)


@router.get("/list")
def list_payroll_runs(
    department: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    """Status per cutoff, for labelling the period picker."""
    runs = db.query(PayrollRun).filter(PayrollRun.department == department).all()
    return {run.cutoff_period: run.status for run in runs}


class GenerateIn(BaseModel):
    department: str
    cutoff_period: str
    employee_count: int = 0
    total_gross: float = 0
    total_net: float = 0


@router.post("/generate")
def mark_generated(
    payload: GenerateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_can_payroll(db, current_user, PAYROLL_PREPARE)
    run = _get_or_new(db, payload.department, payload.cutoff_period)
    if run.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"This payroll is already {run.status.lower()} and can't be generated again.",
        )
    regenerated = run.status != "DRAFT"
    run.status = "GENERATED"
    run.employee_count = payload.employee_count
    run.total_gross = payload.total_gross
    run.total_net = payload.total_net
    run.generated_at = datetime.utcnow()
    run.generated_by = current_user.id
    _log(db, run, "regenerated" if regenerated else "generated", current_user)
    db.commit()
    return _serialize(db, run, current_user, payload.department, payload.cutoff_period)


class TransitionIn(BaseModel):
    department: str
    cutoff_period: str
    action: str
    note: str | None = None


# action -> (allowed from, new status, who, timestamp prefix, note required)
TRANSITIONS = {
    "submit": (("GENERATED",), "FOR_REVIEW", PAYROLL_PREPARE, "submitted", False),
    "approve": (("FOR_REVIEW",), "APPROVED", PAYROLL_APPROVE, "approved", False),
    "return": (("FOR_REVIEW", "APPROVED"), "GENERATED", PAYROLL_APPROVE, None, True),
    "lock": (("APPROVED",), "LOCKED", PAYROLL_RELEASE, "locked", False),
    "mark_paid": (("LOCKED",), "PAID", PAYROLL_RELEASE, "paid", False),
    "unlock": (("LOCKED",), "APPROVED", "superadmin", None, True),
}


@router.post("/transition")
def transition_payroll_run(
    payload: TransitionIn,
    db: Session = Depends(get_db),
    # Not _require_payroll: a Finance approver may have Payroll view-only
    # plus "Approve & Return" -- the step grant below is what counts.
    current_user: User = Depends(get_current_user),
):
    if payload.action not in TRANSITIONS:
        raise HTTPException(status_code=400, detail="Unknown action.")
    allowed_from, new_status, who, stamp, needs_note = TRANSITIONS[payload.action]

    if who != "superadmin":
        ensure_can_payroll(db, current_user, who)
    if who == "superadmin" and _role(current_user) != "superadmin":
        raise HTTPException(status_code=403, detail="Only a superadmin can unlock payroll.")

    note = (payload.note or "").strip() or None
    if needs_note and not note:
        raise HTTPException(status_code=400, detail="Please give a reason.")

    run = _get_or_new(db, payload.department, payload.cutoff_period)
    if run.status not in allowed_from:
        raise HTTPException(
            status_code=409,
            detail=f"Payroll is {run.status.replace('_', ' ').lower()}; it can't be moved that way.",
        )

    run.status = new_status
    if stamp:
        setattr(run, f"{stamp}_at", datetime.utcnow())
        setattr(run, f"{stamp}_by", current_user.id)
    if payload.action in ("return", "unlock"):
        run.return_note = note
        if payload.action == "return":
            run.submitted_at = run.submitted_by = None
            run.approved_at = run.approved_by = None
        else:
            run.locked_at = run.locked_by = None
    _log(db, run, payload.action, current_user, note)
    db.commit()
    return _serialize(db, run, current_user, payload.department, payload.cutoff_period)
