"""Finance -> CA Corrections (same idea as Trip Corrections).

Adjusting what a cash advance owes, or reversing a deduction that was
never taken from pay, no longer happens straight from the Cash Advance
page: someone with Finance -> Cash Advance files a request with a reason,
and an approver (admin, superadmin, or Finance -> CA Corrections) approves
or rejects it. Only approval changes the balance; the person who filed it
can't approve it (superadmin excepted). The checks and the ledger entries
are the ones in app/api/cash_advance_request.py."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api import cash_advance_request as CA
from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.cash_advance_correction import CashAdvanceCorrection
from app.models.cash_advance_request import CashAdvanceRequest
from app.models.employees import Employee
from app.models.user import User
from app.utils.timezone import utc_to_ph
from app.utils.user_display import display_name

router = APIRouter(prefix="/cash-advance-corrections", tags=["Cash Advance Corrections"])

REQUESTER_KEY = "finance.cash_advance"
APPROVER_ROLES = ["admin"]
APPROVER_KEY = "finance.cash_advance_corrections"

_require_requester = require_role_or_module(roles=[], module_key=REQUESTER_KEY)
_require_approver = require_role_or_module(roles=APPROVER_ROLES, module_key=APPROVER_KEY)
_require_viewer = require_role_or_module(
    roles=APPROVER_ROLES, module_key=[REQUESTER_KEY, APPROVER_KEY]
)


def _role(user) -> str:
    return (getattr(user.role, "value", user.role) or "").lower()


def _can(db: Session, user: User, roles: list[str], key: str) -> bool:
    try:
        require_role_or_module(roles=roles, module_key=key)(None, user, db)
        return True
    except HTTPException:
        return False


def _fmt(dt):
    return utc_to_ph(dt).strftime("%b %d, %Y %I:%M %p") if dt else None


def _money(v):
    return float(v) if v is not None else None


def _employee_name(req: CashAdvanceRequest) -> str | None:
    if req is None:
        return None
    if req.employee:
        return f"{req.employee.first_name} {req.employee.last_name}"
    return req.requester.username if req.requester else None


def _serialize(c: CashAdvanceCorrection, user: User, can_approve: bool, can_request: bool) -> dict:
    req = c.cash_advance_request
    mine = c.requested_by_user_id == user.id
    pending = c.status == "pending"
    change = _money(c.change)
    return {
        "id": c.id,
        "kind": c.kind,
        "status": c.status,
        "cash_advance_request_id": c.cash_advance_request_id,
        "reference_no": req.reference_no if req else None,
        "employee_name": _employee_name(req),
        "ca_reason": req.reason if req else None,
        "change": change,
        "amount": _money(c.amount),
        "cutoff_period": c.cutoff_period,
        "deduction_log_id": c.deduction_log_id,
        "owed_before": _money(c.owed_before),
        "balance_before": _money(c.balance_before),
        # What the balance becomes if approved (as of the request).
        "balance_after": (
            round(float(c.balance_before) + (change if c.kind == "adjustment" else float(c.amount or 0)), 2)
            if c.balance_before is not None
            else None
        ),
        "reason": c.reason,
        "requested_by": display_name(c.requested_by) if c.requested_by else None,
        "requested_at": _fmt(c.requested_at),
        "decided_by": display_name(c.decided_by) if c.decided_by else None,
        "decided_at": _fmt(c.decided_at),
        "decision_note": c.decision_note,
        "mine": mine,
        "can_approve": pending and can_approve and (not mine or _role(user) == "superadmin"),
        "can_cancel": pending and mine and can_request,
    }


def _owed_and_balance(db: Session, req: CashAdvanceRequest):
    data = CA._serialize(req, db)
    return data["effective_amount"], data["remaining_balance"]


@router.get("")
def list_corrections(
    status: str | None = Query(None),  # pending | history | all
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_viewer),
):
    q = db.query(CashAdvanceCorrection).options(
        joinedload(CashAdvanceCorrection.cash_advance_request).joinedload(CashAdvanceRequest.employee),
        joinedload(CashAdvanceCorrection.cash_advance_request).joinedload(CashAdvanceRequest.requester),
        joinedload(CashAdvanceCorrection.requested_by),
        joinedload(CashAdvanceCorrection.decided_by),
    )
    if status == "pending":
        q = q.filter(CashAdvanceCorrection.status == "pending")
    elif status == "history":
        q = q.filter(CashAdvanceCorrection.status != "pending")
    rows = q.order_by(CashAdvanceCorrection.requested_at.desc()).limit(500).all()
    can_approve = _can(db, current_user, APPROVER_ROLES, APPROVER_KEY)
    can_request = _can(db, current_user, [], REQUESTER_KEY)
    return {
        "can_approve": can_approve,
        "can_request": can_request,
        "items": [_serialize(c, current_user, can_approve, can_request) for c in rows],
    }


@router.get("/cash-advances")
def search_cash_advances(
    q: str = Query(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_requester),
):
    """Approved cash advances to pick for a new request (fully paid ones
    too -- a reversal can be for one)."""
    query = (
        db.query(CashAdvanceRequest)
        .outerjoin(Employee, Employee.id == CashAdvanceRequest.employee_id)
        .options(joinedload(CashAdvanceRequest.employee), joinedload(CashAdvanceRequest.requester))
        .filter(CashAdvanceRequest.status == "approved")
    )
    text = q.strip()
    if text:
        like = f"%{text}%"
        query = query.filter(
            or_(
                Employee.first_name.ilike(like),
                Employee.last_name.ilike(like),
                CashAdvanceRequest.reference_no.ilike(like),
            )
        )
    rows = query.order_by(CashAdvanceRequest.approved_at.desc()).limit(30).all()
    out = []
    for r in rows:
        data = CA._serialize(r, db)
        out.append({
            "id": r.id,
            "reference_no": r.reference_no,
            "employee_name": data["employee_name"],
            "effective_amount": data["effective_amount"],
            "total_deducted": data["total_deducted"],
            "remaining_balance": data["remaining_balance"],
            "is_fully_paid": data["is_fully_paid"],
        })
    return out


class CorrectionIn(BaseModel):
    cash_advance_request_id: int
    kind: str  # adjustment | reversal
    change: float | None = None  # adjustment
    deduction_log_id: int | None = None  # reversal
    reason: str


@router.post("")
def request_correction(
    payload: CorrectionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_requester),
):
    req = db.query(CashAdvanceRequest).filter(CashAdvanceRequest.id == payload.cash_advance_request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Cash advance not found.")
    owed, balance = _owed_and_balance(db, req)
    c = CashAdvanceCorrection(
        cash_advance_request_id=req.id,
        kind=payload.kind,
        requested_by_user_id=current_user.id,
        owed_before=owed,
        balance_before=balance,
    )
    if payload.kind == "adjustment":
        pending = (
            db.query(CashAdvanceCorrection.id)
            .filter(
                CashAdvanceCorrection.cash_advance_request_id == req.id,
                CashAdvanceCorrection.kind == "adjustment",
                CashAdvanceCorrection.status == "pending",
            )
            .first()
        )
        if pending:
            raise HTTPException(
                status_code=400,
                detail="This cash advance already has an adjustment waiting for approval.",
            )
        change, reason = CA.check_adjustment(db, req, payload.change, payload.reason)
        c.change = change
        c.reason = reason
    elif payload.kind == "reversal":
        if not payload.deduction_log_id:
            raise HTTPException(status_code=400, detail="Pick the deduction to reverse.")
        if payload.deduction_log_id in CA.pending_reversal_log_ids(db, [req.id]):
            raise HTTPException(
                status_code=400, detail="This deduction already has a reversal waiting for approval."
            )
        log, reason = CA.check_reversal(db, req, payload.deduction_log_id, payload.reason)
        c.deduction_log_id = log.id
        c.amount = log.amount
        c.cutoff_period = log.payroll_cutoff_period
        c.reason = reason
    else:
        raise HTTPException(status_code=400, detail="Pick Adjustment or Reversal.")
    db.add(c)
    db.commit()
    db.refresh(c)
    return _serialize(c, current_user, _can(db, current_user, APPROVER_ROLES, APPROVER_KEY), True)


def _get_pending(db: Session, correction_id: int) -> CashAdvanceCorrection:
    c = db.query(CashAdvanceCorrection).filter(CashAdvanceCorrection.id == correction_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Correction request not found.")
    if c.status != "pending":
        raise HTTPException(status_code=400, detail=f"This request was already {c.status}.")
    return c


class DecisionIn(BaseModel):
    note: str | None = None


@router.post("/{correction_id}/approve")
def approve_correction(
    correction_id: int,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_approver),
):
    c = _get_pending(db, correction_id)
    if c.requested_by_user_id == current_user.id and _role(current_user) != "superadmin":
        raise HTTPException(status_code=403, detail="Someone else has to approve your own request.")
    req = (
        db.query(CashAdvanceRequest)
        .filter(CashAdvanceRequest.id == c.cash_advance_request_id)
        .with_for_update()
        .first()
    )
    # Checked again: the balance may have moved since it was filed.
    if c.kind == "adjustment":
        log = CA.apply_adjustment(db, req, float(c.change), c.reason, current_user)
    else:
        log = CA.apply_reversal(db, req, c.deduction_log_id, c.reason, current_user)
    c.status = "approved"
    c.decided_by_user_id = current_user.id
    c.decided_at = datetime.utcnow()
    c.decision_note = (payload.note or "").strip()[:2000] or None
    c.applied_log_id = log.id
    db.commit()
    db.refresh(c)
    return _serialize(c, current_user, True, _can(db, current_user, [], REQUESTER_KEY))


@router.post("/{correction_id}/reject")
def reject_correction(
    correction_id: int,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_approver),
):
    c = _get_pending(db, correction_id)
    note = (payload.note or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="Give the reason for rejecting it.")
    c.status = "rejected"
    c.decided_by_user_id = current_user.id
    c.decided_at = datetime.utcnow()
    c.decision_note = note[:2000]
    db.commit()
    db.refresh(c)
    return _serialize(c, current_user, True, _can(db, current_user, [], REQUESTER_KEY))


@router.post("/{correction_id}/cancel")
def cancel_correction(
    correction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_requester),
):
    c = _get_pending(db, correction_id)
    if c.requested_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the person who filed it can cancel it.")
    c.status = "cancelled"
    c.decided_by_user_id = current_user.id
    c.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(c)
    return _serialize(c, current_user, _can(db, current_user, APPROVER_ROLES, APPROVER_KEY), True)
