from datetime import datetime
from math import ceil

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role_or_module
from app.models.user import User
from app.models.employees import Employee
from app.models.cash_advance_head import CashAdvanceHead
from app.models.cash_advance_request import CashAdvanceRequest
from app.models.cash_advance_deduction_option import CashAdvanceDeductionOption
from app.models.cash_advance_deduction_log import CashAdvanceDeductionLog
from app.models.cash_advance_terms import CashAdvanceTerms
from app.models.notification import Notification
from app.services.notification_service import create_notification
from app.schemas.cash_advance_request import (
    CashAdvanceRequestCreate,
    CashAdvanceReviewAction,
    RecordDeductionCreate,
)

router = APIRouter(prefix="/cash-advance-requests", tags=["Cash Advance Requests"])


def _total_deducted(request_id: int, db: Session) -> float:
    total = (
        db.query(func.coalesce(func.sum(CashAdvanceDeductionLog.amount), 0))
        .filter(CashAdvanceDeductionLog.cash_advance_request_id == request_id)
        .scalar()
    )
    return float(total or 0)


def _serialize(req: CashAdvanceRequest, db: Session) -> dict:
    employee = req.employee
    requester = req.requester
    approver = req.requested_by

    amount = float(req.amount)
    deducted = _total_deducted(req.id, db)
    remaining = round(amount - deducted, 2)
    per_pay = float(req.deduction_per_pay_amount)

    return {
        "id": req.id,
        "employee_id": req.employee_id,
        "employee_name": (
            f"{employee.first_name} {employee.last_name}"
            if employee
            else (requester.username if requester else None)
        ),
        "amount": amount,
        "deduction_option_id": req.deduction_option_id,
        "deduction_per_pay_amount": per_pay,
        "estimated_pay_periods": ceil(amount / per_pay) if per_pay > 0 else None,
        "total_deducted": deducted,
        "remaining_balance": max(remaining, 0),
        "is_fully_paid": remaining <= 0,
        "reason": req.reason,
        "terms_accepted": req.terms_accepted,
        "terms_accepted_at": req.terms_accepted_at,
        "status": req.status,
        "remarks": req.remarks,
        "requested_by_user_id": req.requested_by_user_id,
        "requested_by_name": approver.username if approver else None,
        "approved_by_user_id": req.approved_by_user_id,
        "approved_at": req.approved_at,
        "created_at": req.created_at,
    }


def _can_review(req: CashAdvanceRequest, current_user: User, db: Session) -> bool:
    if req.requested_by_user_id == current_user.id:
        return True
    if current_user.role == "superadmin":
        return True
    employee = req.employee
    if not employee or not employee.department:
        return False
    # Live check against the CURRENT cash-advance head, not just whoever
    # was recorded as requested_by_user_id at filing time -- so if the
    # assignment changes after a request is already pending, the new
    # head can still review it (matches the equivalent DepartmentHead
    # fallback this used to do, just pointed at the cash-advance-specific
    # hierarchy now).
    head_entry = (
        db.query(CashAdvanceHead)
        .filter(CashAdvanceHead.department == employee.department)
        .first()
    )
    return bool(head_entry and head_entry.head_user_id == current_user.id)


@router.post("/")
def file_cash_advance_request(
    payload: CashAdvanceRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Superadmin accounts cannot file cash advance requests.",
        )

    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0.")

    terms = db.query(CashAdvanceTerms).order_by(CashAdvanceTerms.id.asc()).first()

    max_loan_amount = terms.max_loan_amount if terms else None
    if max_loan_amount is not None and payload.amount > float(max_loan_amount):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Amount exceeds the maximum loanable amount of "
                f"{float(max_loan_amount):.2f}."
            ),
        )

    option = (
        db.query(CashAdvanceDeductionOption)
        .filter(
            CashAdvanceDeductionOption.id == payload.deduction_option_id,
            CashAdvanceDeductionOption.is_active.is_(True),
        )
        .first()
    )
    if not option:
        raise HTTPException(
            status_code=400,
            detail="Selected deduction-per-pay amount is not available.",
        )

    max_pay_periods = terms.max_pay_periods if terms else 6
    estimated_periods = ceil(payload.amount / float(option.amount))
    if estimated_periods > max_pay_periods:
        raise HTTPException(
            status_code=400,
            detail=(
                f"At {option.amount:.2f} per pay, this would take "
                f"{estimated_periods} pay periods, which exceeds the "
                f"maximum of {max_pay_periods}. Choose a higher deduction "
                "amount."
            ),
        )
    if terms and terms.content.strip() and not payload.terms_accepted:
        raise HTTPException(
            status_code=400,
            detail="You must acknowledge the terms and conditions to proceed.",
        )

    employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
    )
    if not employee or not employee.department:
        raise HTTPException(
            status_code=400,
            detail="Your account isn't linked to an employee department.",
        )

    # Cash advance requests route to the department's Cash Advance
    # Immediate Head (a hierarchy separate from the general/overtime
    # DepartmentHead -- see app/models/cash_advance_head.py). If the
    # department hasn't had one configured yet, fall back to a
    # superadmin rather than blocking the request outright -- an
    # unconfigured hierarchy shouldn't stop an employee from filing.
    head_entry = (
        db.query(CashAdvanceHead)
        .filter(CashAdvanceHead.department == employee.department)
        .first()
    )

    if head_entry:
        approver_user_id = head_entry.head_user_id
    else:
        fallback_superadmin = (
            db.query(User).filter(User.role == "superadmin").first()
        )
        if not fallback_superadmin:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No cash advance head has been set for the "
                    f"{employee.department} department yet, and no "
                    "superadmin account exists to fall back to. Ask an "
                    "admin to set this up in Reporting Hierarchy."
                ),
            )
        approver_user_id = fallback_superadmin.id

    request = CashAdvanceRequest(
        user_id=current_user.id,
        employee_id=current_user.employee_id,
        requested_by_user_id=approver_user_id,
        amount=payload.amount,
        deduction_option_id=option.id,
        deduction_per_pay_amount=option.amount,
        reason=payload.reason,
        terms_accepted=bool(payload.terms_accepted),
        terms_accepted_at=(
            datetime.utcnow() if payload.terms_accepted else None
        ),
        status="pending",
    )

    db.add(request)
    db.commit()
    db.refresh(request)

    # Notify the finance/approver side that a new request needs review --
    # surfaced via GET /cash-advance-requests/alerts (a bell/notification,
    # same pattern as the trip "hub alerts" feature). Not targeted at the
    # specific approver (Notification has no recipient/role column, see
    # app/models/notification.py) -- alerts.py restricts who can list
    # these to superadmin, matching who reviews cash advances today.
    create_notification(
        db=db,
        type_="CASH_ADVANCE_REQUESTED",
        driver_id=current_user.id,
        message=(
            f"{current_user.username} requested a cash advance of "
            f"₱{float(payload.amount):,.2f} (request #{request.id})."
        ),
    )

    return _serialize(request, db)


@router.get("/mine")
def get_my_cash_advance_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    requests = (
        db.query(CashAdvanceRequest)
        .options(
            joinedload(CashAdvanceRequest.employee),
            joinedload(CashAdvanceRequest.requested_by),
        )
        .filter(CashAdvanceRequest.user_id == current_user.id)
        .order_by(CashAdvanceRequest.created_at.desc())
        .all()
    )
    return [_serialize(r, db) for r in requests]


@router.get("/my-balance")
def get_my_cash_advance_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Total outstanding balance across all of the caller's approved,
    not-yet-fully-paid cash advance requests -- for a dashboard tile."""
    approved = (
        db.query(CashAdvanceRequest)
        .filter(
            CashAdvanceRequest.user_id == current_user.id,
            CashAdvanceRequest.status == "approved",
        )
        .all()
    )

    serialized = [_serialize(r, db) for r in approved]
    outstanding = [r for r in serialized if not r["is_fully_paid"]]

    return {
        "total_outstanding": round(
            sum(r["remaining_balance"] for r in outstanding), 2
        ),
        "requests": outstanding,
    }


@router.post("/{request_id}/cancel")
def cancel_cash_advance_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = (
        db.query(CashAdvanceRequest)
        .filter(CashAdvanceRequest.id == request_id)
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Cash advance request not found")
    if request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only cancel your own requests")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending requests can be cancelled")

    request.status = "cancelled"
    db.commit()
    db.refresh(request)
    return _serialize(request, db)


@router.get("/for-my-approval")
def get_requests_for_my_approval(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pending = (
        db.query(CashAdvanceRequest)
        .options(
            joinedload(CashAdvanceRequest.employee),
            joinedload(CashAdvanceRequest.requested_by),
        )
        .filter(CashAdvanceRequest.status == "pending")
        .order_by(CashAdvanceRequest.created_at.asc())
        .all()
    )
    mine = [r for r in pending if _can_review(r, current_user, db)]
    return [_serialize(r, db) for r in mine]


@router.post("/{request_id}/approve")
def approve_cash_advance_request(
    request_id: int,
    payload: CashAdvanceReviewAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = (
        db.query(CashAdvanceRequest)
        .options(joinedload(CashAdvanceRequest.employee))
        .filter(CashAdvanceRequest.id == request_id)
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Cash advance request not found")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending requests can be approved")
    if not _can_review(request, current_user, db):
        raise HTTPException(
            status_code=403, detail="You are not authorized to approve this request."
        )

    request.status = "approved"
    request.remarks = payload.remarks
    request.approved_by_user_id = current_user.id
    request.approved_at = datetime.utcnow()

    db.commit()
    db.refresh(request)
    return _serialize(request, db)


@router.post("/{request_id}/reject")
def reject_cash_advance_request(
    request_id: int,
    payload: CashAdvanceReviewAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = (
        db.query(CashAdvanceRequest)
        .options(joinedload(CashAdvanceRequest.employee))
        .filter(CashAdvanceRequest.id == request_id)
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Cash advance request not found")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending requests can be reviewed")
    if not _can_review(request, current_user, db):
        raise HTTPException(
            status_code=403, detail="You are not authorized to reject this request."
        )

    request.status = "rejected"
    request.remarks = payload.remarks
    request.approved_by_user_id = current_user.id
    request.approved_at = datetime.utcnow()

    db.commit()
    db.refresh(request)
    return _serialize(request, db)


# =========================
# BALANCE LEDGER (superadmin)
# =========================


@router.get("/balances")
def list_outstanding_balances(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role_or_module(roles=[], module_key="finance.cash_advance")
    ),
):
    """Every approved request with a remaining balance > 0 -- the
    superadmin page's outstanding-balances list."""
    approved = (
        db.query(CashAdvanceRequest)
        .options(
            joinedload(CashAdvanceRequest.employee),
            joinedload(CashAdvanceRequest.requester),
        )
        .filter(CashAdvanceRequest.status == "approved")
        .order_by(CashAdvanceRequest.approved_at.desc())
        .all()
    )
    serialized = [_serialize(r, db) for r in approved]
    return [r for r in serialized if not r["is_fully_paid"]]


@router.post("/{request_id}/record-deduction")
def record_deduction(
    request_id: int,
    payload: RecordDeductionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role_or_module(roles=[], module_key="finance.cash_advance")
    ),
):
    """Manually records one deduction event against a request (e.g. once
    per payroll cutoff) -- not yet wired into automatic payslip
    generation, so superadmin posts these as deductions actually happen."""
    request = (
        db.query(CashAdvanceRequest)
        .filter(CashAdvanceRequest.id == request_id)
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Cash advance request not found")
    if request.status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Deductions can only be recorded for approved requests.",
        )

    remaining = float(request.amount) - _total_deducted(request.id, db)
    if remaining <= 0:
        raise HTTPException(
            status_code=400, detail="This cash advance is already fully paid."
        )

    amount = (
        payload.amount
        if payload.amount is not None
        else float(request.deduction_per_pay_amount)
    )
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0.")
    if amount > remaining:
        raise HTTPException(
            status_code=400,
            detail=f"Amount exceeds the remaining balance of {remaining:.2f}.",
        )

    log = CashAdvanceDeductionLog(
        cash_advance_request_id=request.id,
        amount=amount,
        note=payload.note,
        recorded_by_user_id=current_user.id,
    )
    db.add(log)
    db.commit()

    db.refresh(request)
    return _serialize(request, db)


# =========================
# ALERTS (superadmin/finance) -- new-request notifications
#
# Mirrors the trip "hub alerts" pattern (see GET /admin/trips/hub-alerts):
# CASH_ADVANCE_REQUESTED rows are created at filing time in
# file_cash_advance_request() above; these two endpoints let the
# notification bell list and dismiss them.
# =========================


@router.get("/alerts")
def get_cash_advance_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role_or_module(roles=[], module_key="finance.cash_advance")
    ),
):
    alerts = (
        db.query(Notification)
        .filter(
            Notification.type == "CASH_ADVANCE_REQUESTED",
            Notification.status == "PENDING",
        )
        .order_by(Notification.created_at.desc())
        .all()
    )
    return [
        {
            "id": alert.id,
            "message": alert.message,
            "created_at": alert.created_at,
        }
        for alert in alerts
    ]


@router.post("/alerts/{notification_id}/acknowledge")
def acknowledge_cash_advance_alert(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role_or_module(roles=[], module_key="finance.cash_advance")
    ),
):
    alert = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.type == "CASH_ADVANCE_REQUESTED",
        )
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")

    alert.status = "ACKNOWLEDGED"
    alert.reviewed_by_admin_id = current_user.id
    alert.reviewed_at = datetime.utcnow()

    db.commit()

    return {"message": "Alert acknowledged."}


# =========================
# ALL REQUESTS (superadmin/finance) -- full history, every status
# =========================


@router.get("/all")
def list_all_cash_advance_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role_or_module(roles=[], module_key="finance.cash_advance")
    ),
):
    """Every cash advance request regardless of status or who's the
    approver -- for the Finance module's full-history view, distinct
    from /for-my-approval (pending + reviewable-by-caller only) and
    /balances (approved + still-outstanding only)."""
    requests = (
        db.query(CashAdvanceRequest)
        .options(
            joinedload(CashAdvanceRequest.employee),
            joinedload(CashAdvanceRequest.requested_by),
        )
        .order_by(CashAdvanceRequest.created_at.desc())
        .all()
    )
    return [_serialize(r, db) for r in requests]
