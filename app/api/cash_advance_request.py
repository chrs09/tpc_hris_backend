from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from math import ceil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    has_editable_grant,
    require_role_or_module,
)
from app.models.user import User
from app.models.employees import Employee
from app.utils.user_display import display_name
from app.services.approval_chain import (
    acting_index,
    skipped_for,
    log_skipped,
    append_log,
    describe_chain,
    dump_chain,
    load_json_list,
    resolve_chain,
)
from app.models.cash_advance_request import CashAdvanceRequest
from app.models.cash_advance_deduction_option import CashAdvanceDeductionOption
from app.models.cash_advance_deduction_log import CashAdvanceDeductionLog
from app.models.cash_advance_terms import CashAdvanceTerms
from app.models.notification import Notification
from app.services.notification_service import create_notification
from app.models.files import File as FileModel
from app.services.file_service import FileService

# Photo of the transfer / hand-over (GCash, bank, signed voucher) proving
# the approved cash advance was sent -- uploaded at the final approval or
# with Record Release.
RECEIPT_DOC = "CA_RELEASE_RECEIPT"



def _utc(value):
    """Stored times are naive UTC; send them marked as UTC ("...+00:00") so
    browsers and the phone app show Philippine time, not 8 hours early."""
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None

def _receipt_url(db: Session, request_id: int) -> str | None:
    row = (
        db.query(FileModel.file_url)
        .filter(
            FileModel.entity_type == "cash_advance",
            FileModel.entity_id == request_id,
            FileModel.document_type == RECEIPT_DOC,
        )
        .order_by(FileModel.id.desc())
        .first()
    )
    return row[0] if row else None
from app.schemas.cash_advance_request import (
    CashAdvanceExceptionRequest,
    CashAdvanceRequestCreate,
    CashAdvanceReviewAction,
    RecordDeductionCreate,
    OpeningBalanceCreate,
    ReleaseInfoUpdate,
    RevisedTermsResponse,
)

router = APIRouter(prefix="/cash-advance-requests", tags=["Cash Advance Requests"])


def _total_deducted(request_id: int, db: Session) -> float:
    total = (
        db.query(func.coalesce(func.sum(CashAdvanceDeductionLog.amount), 0))
        .filter(CashAdvanceDeductionLog.cash_advance_request_id == request_id)
        .scalar()
    )
    return float(total or 0)


def _display_status(req: CashAdvanceRequest) -> str:
    """What to show: status, with an approved request's next stage --
    "awaiting_acceptance" (revised terms) or "released" (money handed over).
    `status` itself stays "approved" for balances and payroll."""
    if req.status == "approved":
        if req.revised_terms_status == "pending":
            return "awaiting_acceptance"
        if req.released_at:
            return "released"
    return req.status


def _ensure_terms_settled(request: CashAdvanceRequest) -> None:
    if request.revised_terms_status == "pending":
        raise HTTPException(
            status_code=400,
            detail="The employee hasn't accepted the revised terms yet.",
        )


def _serialize(req: CashAdvanceRequest, db: Session) -> dict:
    employee = req.employee
    requester = req.requester
    approver = req.requested_by

    amount = float(req.amount)
    approved_amount = (
        float(req.approved_amount) if req.approved_amount is not None else None
    )
    # Balance math runs off the APPROVED amount once one exists (the
    # approver may have granted less than requested) -- falls back to
    # the requested amount before approval, when approved_amount is
    # still null.
    payable_amount = approved_amount if approved_amount is not None else amount
    deducted = _total_deducted(req.id, db)
    remaining = round(payable_amount - deducted, 2)
    per_pay = float(req.deduction_per_pay_amount)

    return {
        "id": req.id,
        **_exception_fields(req),
        "employee_id": req.employee_id,
        "employee_name": (
            f"{employee.first_name} {employee.last_name}"
            if employee
            else (requester.username if requester else None)
        ),
        "amount": amount,
        "approved_amount": approved_amount,
        "deduction_option_id": req.deduction_option_id,
        "deduction_per_pay_amount": per_pay,
        "estimated_pay_periods": (
            ceil(payable_amount / per_pay) if per_pay > 0 else None
        ),
        "total_deducted": deducted,
        "remaining_balance": max(remaining, 0),
        "is_fully_paid": remaining <= 0,
        "reason": req.reason,
        "date_needed": req.date_needed.isoformat() if req.date_needed else None,
        "terms_accepted": req.terms_accepted,
        "terms_accepted_at": _utc(req.terms_accepted_at),
        "status": req.status,
        "display_status": _display_status(req),
        "revised_terms_status": req.revised_terms_status,
        "revised_terms_pending": req.revised_terms_status == "pending" and req.status == "approved",
        "revised_terms_previous_amount": (
            float(req.revised_terms_previous_amount)
            if req.revised_terms_previous_amount is not None
            else None
        ),
        "revised_terms_previous_per_pay": (
            float(req.revised_terms_previous_per_pay)
            if req.revised_terms_previous_per_pay is not None
            else None
        ),
        "revised_terms_required_at": _utc(req.revised_terms_required_at),
        "revised_terms_responded_at": _utc(req.revised_terms_responded_at),
        "revised_terms_remarks": req.revised_terms_remarks,
        "remarks": req.remarks,
        "requested_by_user_id": req.requested_by_user_id,
        "requested_by_name": approver.username if approver else None,
        "approved_by_user_id": req.approved_by_user_id,
        # Who gave the final approval / rejection (full name).
        "approved_by_name": (
            display_name(req.approved_by) if req.approved_by else None
        ),
        "approved_at": _utc(req.approved_at),
        "release_reference": req.release_reference,
        "release_receipt_url": _receipt_url(db, req.id),
        "is_archived": bool(req.is_archived),
        "released_at": _utc(req.released_at),
        "released_by_name": (
            req.released_by.username if req.released_by else None
        ),
        "created_at": _utc(req.created_at),
        # False when the viewer's step was passed up because they're
        # absent / on leave today (see for-my-approval).
        "can_act": getattr(req, "_can_act", True),
        "can_request_exception": getattr(req, "_can_exception", False),
        "viewer_away": getattr(req, "_away", None),
        # Org chart approval progress (empty when routed the old way).
        **describe_chain(
            db,
            req.approval_chain,
            req.approval_step,
            req.approval_log,
            req.status != "pending",
        ),
    }


def _exception_fields(req: CashAdvanceRequest) -> dict:
    return {
        "exception_status": req.exception_status,
        "awaiting_exception": req.exception_status == "pending" and req.status == "pending",
        "exception_amount": (
            float(req.exception_amount) if req.exception_amount is not None else None
        ),
        "exception_pay_periods": req.exception_pay_periods,
        "exception_deduction_per_pay": (
            float(req.exception_deduction_per_pay)
            if req.exception_deduction_per_pay is not None
            else None
        ),
        "exception_reason": req.exception_reason,
        "exception_requested_by_name": (
            display_name(req.exception_requested_by) if req.exception_requested_by else None
        ),
        "exception_requested_at": _utc(req.exception_requested_at),
        "exception_approver_user_id": req.exception_approver_user_id,
        "exception_approver_name": (
            display_name(req.exception_approver) if req.exception_approver else None
        ),
        "exception_decided_at": _utc(req.exception_decided_at),
        "exception_remarks": req.exception_remarks,
    }


def _exception_approver(db: Session) -> User | None:
    """Cash Advance Settings -> Exception approver, else a superadmin."""
    terms = db.query(CashAdvanceTerms).order_by(CashAdvanceTerms.id.asc()).first()
    if terms and terms.exception_approver_user_id:
        user = (
            db.query(User)
            .filter(User.id == terms.exception_approver_user_id, User.is_active.is_(True))
            .first()
        )
        if user:
            return user
    return db.query(User).filter(User.role == "superadmin", User.is_active.is_(True)).first()


def _is_superadmin(user: User) -> bool:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return role == "superadmin"


def _can_review(req: CashAdvanceRequest, current_user: User, db: Session) -> bool:
    # An exception waiting for its approver: only they (or a superadmin)
    # can act until it's decided.
    if req.exception_status == "pending":
        return req.exception_approver_user_id == current_user.id or _is_superadmin(
            current_user
        )
    if not req.approval_chain and req.requested_by_user_id == current_user.id:
        return True
    if current_user.role == "superadmin":
        return True
    # Granted Cash Advance Approvals with "Can edit: Yes".
    if has_editable_grant(db, current_user, ["finance.cash_advance"]):
        return True
    if req.approval_chain:
        # Org chart routing: only the approver whose turn it is -- passed
        # up the chain while that approver is absent / on leave today.
        chain = [int(i) for i in load_json_list(req.approval_chain)]
        return acting_index(db, chain, req.approval_step, current_user.id)[0] is not None
    return False


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
    today_ph = datetime.now(ZoneInfo("Asia/Manila")).date()
    if payload.date_needed and payload.date_needed < today_ph:
        raise HTTPException(status_code=400, detail="Date Needed can't be in the past.")

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

    max_active_requests = terms.max_active_requests if terms else None
    if max_active_requests is not None:
        active_requests = (
            db.query(CashAdvanceRequest)
            .filter(
                CashAdvanceRequest.user_id == current_user.id,
                CashAdvanceRequest.status.in_(["pending", "approved"]),
            )
            .all()
        )
        # "approved" only counts while still outstanding -- a fully paid
        # off approved request shouldn't keep counting against the cap.
        # Uses approved_amount (what the approver actually granted) once
        # it's set, rather than the original requested amount.
        still_active = [
            r
            for r in active_requests
            if r.status == "pending"
            or (
                float(r.approved_amount if r.approved_amount is not None else r.amount)
                - _total_deducted(r.id, db)
                > 0
            )
        ]
        if len(still_active) >= max_active_requests:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"You already have {len(still_active)} active cash "
                    f"advance request(s), which is the maximum of "
                    f"{max_active_requests} allowed at once. Settle or "
                    "cancel an existing one before filing another."
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
    if not employee:
        raise HTTPException(
            status_code=400,
            detail="Your account isn't linked to an employee.",
        )

    # Org Chart: every head up the layers who approves cash advances, in
    # order. Nobody set up there -> a superadmin reviews it.
    chain = resolve_chain(db, employee, current_user, "cash_advance")
    if not chain and not employee.department:
        raise HTTPException(
            status_code=400,
            detail="Your account isn't linked to an employee department.",
        )

    if chain:
        approver_user_id = chain[0]
    else:
        fallback_superadmin = (
            db.query(User).filter(User.role == "superadmin").first()
        )
        if not fallback_superadmin:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No one approves cash advances for you yet. Ask an "
                    "admin to tick Cash Advance for your head on the Org Chart."
                ),
            )
        approver_user_id = fallback_superadmin.id

    request = CashAdvanceRequest(
        user_id=current_user.id,
        employee_id=current_user.employee_id,
        requested_by_user_id=approver_user_id,
        approval_chain=dump_chain(chain),
        approval_step=0,
        amount=payload.amount,
        deduction_option_id=option.id,
        deduction_per_pay_amount=option.amount,
        reason=payload.reason,
        date_needed=payload.date_needed,
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
    outstanding = [
        r for r in serialized if not r["is_fully_paid"] and not r["revised_terms_pending"]
    ]

    return {
        "total_outstanding": round(
            sum(r["remaining_balance"] for r in outstanding), 2
        ),
        "requests": outstanding,
    }


@router.post("/{request_id}/revised-terms")
def respond_to_revised_terms(
    request_id: int,
    payload: RevisedTermsResponse,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The employee accepts revised terms (the request can now be released)
    or declines them (it's cancelled -- no money has gone out). Only the
    employee can answer; nobody can accept on their behalf."""
    request = (
        db.query(CashAdvanceRequest)
        .filter(CashAdvanceRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Cash advance request not found")
    if request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the employee can answer revised terms.")
    if request.status != "approved" or request.revised_terms_status != "pending":
        raise HTTPException(status_code=400, detail="There are no revised terms waiting for you.")

    remarks = (payload.remarks or "").strip() or None
    request.revised_terms_status = "accepted" if payload.accept else "declined"
    request.revised_terms_responded_at = datetime.utcnow()
    request.revised_terms_remarks = remarks
    request.approval_log = append_log(
        request.approval_log,
        current_user,
        "accepted revised terms" if payload.accept else "declined revised terms",
        remarks,
    )
    if not payload.accept:
        request.status = "cancelled"
    db.commit()

    create_notification(
        db=db,
        type_="CASH_ADVANCE_REQUESTED",
        driver_id=current_user.id,
        message=(
            f"{current_user.username} accepted the revised terms of cash advance "
            f"#{request.id} -- ready for release."
            if payload.accept
            else f"{current_user.username} declined the revised terms of cash advance "
            f"#{request.id} -- it was cancelled."
        ),
    )
    db.refresh(request)
    return _serialize(request, db)


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
    mine = []
    for r in pending:
        if _can_review(r, current_user, db):
            r._can_act = True
            # The last approver (or a superadmin) may ask for an exception.
            r._can_exception = r.exception_status != "pending" and (
                _is_last_step(db, r, current_user) or _is_superadmin(current_user)
            )
            mine.append(r)
        elif r.approval_chain:
            # Their step was passed up because they're out today: shown,
            # but they can't approve / reject it.
            away = skipped_for(
                db, [int(i) for i in load_json_list(r.approval_chain)], r.approval_step, current_user.id
            )
            if away:
                r._can_act = False
                r._away = away
                mine.append(r)
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

    if request.exception_status == "pending":
        # The exception approver allows it: approved with the exception's
        # amount and repayment term.
        _apply_exception(request)
        request.exception_status = "approved"
        request.exception_decided_at = datetime.utcnow()
        request.exception_remarks = payload.remarks
        request.approval_log = append_log(
            request.approval_log,
            current_user,
            "approved",
            payload.remarks or "Exception approved",
            approved_amount=float(request.approved_amount),
        )
        request.status = "approved"
        request.remarks = payload.remarks
        request.approved_by_user_id = current_user.id
        request.approved_at = datetime.utcnow()
        db.commit()
        db.refresh(request)
        return _serialize(request, db)

    if payload.approved_amount is not None:
        if payload.approved_amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Approved amount must be greater than 0.",
            )
        if payload.approved_amount > float(request.amount):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Approved amount can't exceed the requested amount of "
                    f"{float(request.amount):.2f}."
                ),
            )
        request.approved_amount = payload.approved_amount
    elif request.approved_amount is None:
        # Not overridden -- approve the full requested amount (or keep
        # what an earlier head in the chain approved).
        request.approved_amount = request.amount

    chain = [int(i) for i in load_json_list(request.approval_chain)]
    acting, skipped = (
        acting_index(db, chain, request.approval_step, current_user.id)
        if chain
        else (None, [])
    )
    # Approvers before this one who are out today were skipped.
    request.approval_log = log_skipped(db, request.approval_log, chain, skipped)
    request.approval_log = append_log(
        request.approval_log,
        current_user,
        "approved",
        payload.remarks,
        approved_amount=float(request.approved_amount),
    )

    # Org chart chain: pass it to the next head up. (A superadmin or a
    # Cash Advance "Can edit" grant who isn't the one up now finishes it.)
    if chain and acting is not None and acting < len(chain) - 1:
        request.approval_step = acting + 1
        request.requested_by_user_id = chain[request.approval_step]
        db.commit()
        db.refresh(request)
        return _serialize(request, db)

    if chain and acting is not None:
        request.approval_step = acting
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

    if request.exception_status == "pending":
        # Exception turned down: back to the approver who asked, who can
        # still approve within the policy or reject the request.
        request.exception_status = "rejected"
        request.exception_decided_at = datetime.utcnow()
        request.exception_remarks = payload.remarks
        request.requested_by_user_id = request.exception_requested_by_user_id
        request.approval_log = append_log(
            request.approval_log,
            current_user,
            "exception rejected",
            payload.remarks,
        )
        db.commit()
        db.refresh(request)
        return _serialize(request, db)

    request.approval_log = append_log(
        request.approval_log, current_user, "rejected", payload.remarks
    )
    request.status = "rejected"
    request.remarks = payload.remarks
    request.approved_by_user_id = current_user.id
    request.approved_at = datetime.utcnow()

    db.commit()
    db.refresh(request)
    return _serialize(request, db)


# =========================
# EXCEPTION (above the policy limit)
# =========================
def _apply_exception(request: CashAdvanceRequest) -> None:
    """Use the exception's amount and repayment for the approval. If that
    differs from what the employee agreed to when filing, they have to
    accept the revised terms first (see respond_to_revised_terms)."""
    previous_amount = float(request.amount)
    previous_per_pay = float(request.deduction_per_pay_amount)
    if (
        round(float(request.exception_amount), 2) != round(previous_amount, 2)
        or round(float(request.exception_deduction_per_pay), 2) != round(previous_per_pay, 2)
    ):
        request.revised_terms_status = "pending"
        request.revised_terms_previous_amount = previous_amount
        request.revised_terms_previous_per_pay = previous_per_pay
        request.revised_terms_required_at = datetime.utcnow()
        request.revised_terms_responded_at = None
        request.revised_terms_remarks = None
    request.approved_amount = request.exception_amount
    request.deduction_per_pay_amount = request.exception_deduction_per_pay
    # Custom repayment -- not one of the preset per-pay options.
    request.deduction_option_id = None


def _is_last_step(db: Session, request: CashAdvanceRequest, user: User) -> bool:
    """The approver who would give the final approval right now."""
    chain = [int(i) for i in load_json_list(request.approval_chain)]
    if chain:
        acting, _ = acting_index(db, chain, request.approval_step, user.id)
        return acting is not None and acting == len(chain) - 1
    return request.requested_by_user_id == user.id


@router.post("/{request_id}/request-exception")
def request_cash_advance_exception(
    request_id: int,
    payload: CashAdvanceExceptionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The LAST approver asks the exception approver (Cash Advance
    Settings) to allow more than the policy -- e.g. ₱8,000 when the limit
    is ₱5,000 -- with its own repayment term and a reason. The exception
    approver then approves (request approved with these figures) or
    rejects (back to this approver)."""
    request = (
        db.query(CashAdvanceRequest)
        .options(joinedload(CashAdvanceRequest.employee))
        .filter(CashAdvanceRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Cash advance request not found")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending requests can get an exception.")
    if request.exception_status == "pending":
        raise HTTPException(status_code=400, detail="An exception is already waiting for approval.")
    if not (_is_last_step(db, request, current_user) or _is_superadmin(current_user)):
        raise HTTPException(
            status_code=403,
            detail="Only the last approver can ask for an exception.",
        )

    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Give the reason for the exception.")
    if payload.amount <= 0 or payload.amount > 10_000_000:
        raise HTTPException(status_code=400, detail="Enter a valid amount.")
    if payload.pay_periods <= 0 or payload.pay_periods > 120:
        raise HTTPException(
            status_code=400, detail="Repayment term must be between 1 and 120 pay periods."
        )
    per_pay = ceil(payload.amount * 100 / payload.pay_periods) / 100

    approver = _exception_approver(db)
    if not approver:
        raise HTTPException(
            status_code=400,
            detail="No exception approver is set. Set one in Cash Advance Settings.",
        )

    request.exception_amount = payload.amount
    request.exception_pay_periods = payload.pay_periods
    request.exception_deduction_per_pay = per_pay
    request.exception_reason = reason[:2000]
    request.exception_requested_by_user_id = current_user.id
    request.exception_requested_at = datetime.utcnow()
    request.exception_approver_user_id = approver.id
    request.exception_decided_at = None
    request.exception_remarks = None
    request.approval_log = append_log(
        request.approval_log,
        current_user,
        "exception requested",
        reason,
        approved_amount=float(payload.amount),
    )

    if approver.id == current_user.id:
        # The exception approver is the last approver too: approve it now.
        _apply_exception(request)
        request.exception_status = "approved"
        request.exception_decided_at = datetime.utcnow()
        request.status = "approved"
        request.approved_by_user_id = current_user.id
        request.approved_at = datetime.utcnow()
    else:
        request.exception_status = "pending"
        # "Waiting on" shows the exception approver.
        request.requested_by_user_id = approver.id

    db.commit()
    db.refresh(request)
    return _serialize(request, db)


# =========================
# DEDUCTION HISTORY -- every deduction across all cash advances, newest
# first: payroll ones (with their cutoff and that payroll's status) and
# ones recorded by hand, each with the advance's balance after it.
# =========================


@router.get("/deductions")
def list_deduction_history(
    date_from: str | None = None,
    date_to: str | None = None,
    source: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role_or_module(roles=[], module_key="finance.cash_advance")
    ),
):
    """`date_from` / `date_to` ("YYYY-MM-DD", PH dates the deduction was
    recorded); `source` "payroll" or "manual"."""
    from datetime import date as _date, timedelta

    from app.models.payroll_deductions import PayrollDeduction
    from app.models.payroll_run import PayrollRun
    from app.utils.timezone import ph_to_utc

    try:
        start = _date.fromisoformat(date_from) if date_from else None
        end = _date.fromisoformat(date_to) if date_to else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD.")

    # Every log of the advances involved, so each row's balance-after
    # counts the deductions before it even outside the date range.
    logs = (
        db.query(CashAdvanceDeductionLog)
        .options(
            joinedload(CashAdvanceDeductionLog.recorded_by),
            joinedload(CashAdvanceDeductionLog.cash_advance_request).joinedload(
                CashAdvanceRequest.employee
            ),
            joinedload(CashAdvanceDeductionLog.cash_advance_request).joinedload(
                CashAdvanceRequest.requester
            ),
        )
        .order_by(CashAdvanceDeductionLog.recorded_at, CashAdvanceDeductionLog.id)
        .all()
    )

    paid_so_far = {}
    balance_after = {}
    for log in logs:
        req = log.cash_advance_request
        payable = float(req.approved_amount if req.approved_amount is not None else req.amount)
        paid_so_far[req.id] = paid_so_far.get(req.id, 0) + float(log.amount)
        balance_after[log.id] = round(max(payable - paid_so_far[req.id], 0), 2)

    lo = ph_to_utc(datetime.combine(start, datetime.min.time())) if start else None
    hi = ph_to_utc(datetime.combine(end + timedelta(days=1), datetime.min.time())) if end else None
    shown = [
        log
        for log in logs
        if (lo is None or log.recorded_at >= lo)
        and (hi is None or log.recorded_at < hi)
        and (
            not source
            or (source == "payroll" and log.payroll_cutoff_period)
            or (source == "manual" and not log.payroll_cutoff_period)
        )
    ]

    # Payroll status of each (employee, cutoff): the department comes from
    # the saved payroll row, the status from that department's run.
    def employee_of(req):
        if req.employee_id:
            return req.employee_id
        return req.requester.employee_id if req.requester else None

    cutoffs = {log.payroll_cutoff_period for log in shown if log.payroll_cutoff_period}
    dept_of = {}
    if cutoffs:
        for emp_id, cutoff, dept in db.query(
            PayrollDeduction.employee_id,
            PayrollDeduction.cutoff_period,
            PayrollDeduction.department,
        ).filter(PayrollDeduction.cutoff_period.in_(cutoffs)):
            dept_of[(emp_id, cutoff)] = dept
    run_status = {}
    for run in db.query(PayrollRun).filter(
        PayrollRun.department.in_(set(dept_of.values()) or {""})
    ):
        key = (run.department, f"{run.period_start.isoformat()}_{run.period_end.isoformat()}")
        run_status[key] = run.status

    rows = []
    for log in reversed(shown):
        req = log.cash_advance_request
        employee = req.employee
        emp_id = employee_of(req)
        cutoff = log.payroll_cutoff_period
        dept = dept_of.get((emp_id, cutoff)) if cutoff else None
        rows.append({
            "id": log.id,
            "recorded_at": _utc(log.recorded_at),
            "amount": float(log.amount),
            "source": "payroll" if cutoff else "manual",
            "cutoff_period": cutoff,
            "department": dept,
            "payroll_status": run_status.get((dept, cutoff)) if dept else None,
            "note": log.note,
            "recorded_by_name": display_name(log.recorded_by) if log.recorded_by else None,
            "request_id": req.id,
            "employee_id": emp_id,
            "employee_name": (
                f"{employee.first_name} {employee.last_name}"
                if employee
                else (req.requester.username if req.requester else None)
            ),
            "request_amount": float(
                req.approved_amount if req.approved_amount is not None else req.amount
            ),
            "request_reason": req.reason,
            "balance_after": balance_after[log.id],
        })
    return rows


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
    return [
        r for r in serialized if not r["is_fully_paid"] and not r["revised_terms_pending"]
    ]


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
    _ensure_terms_settled(request)

    payable_amount = (
        float(request.approved_amount)
        if request.approved_amount is not None
        else float(request.amount)
    )
    remaining = payable_amount - _total_deducted(request.id, db)
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


@router.get("/{request_id}/transactions")
def get_deduction_transactions(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role_or_module(roles=[], module_key="finance.cash_advance")
    ),
):
    """The full ledger of deductions recorded against one request, newest
    first -- what the Outstanding Balances page's "Transaction History"
    view shows. Separate from `record_deduction` above (which still adds
    a new entry); this only reads."""
    request = (
        db.query(CashAdvanceRequest)
        .filter(CashAdvanceRequest.id == request_id)
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Cash advance request not found")

    logs = (
        db.query(CashAdvanceDeductionLog)
        .options(joinedload(CashAdvanceDeductionLog.recorded_by))
        .filter(CashAdvanceDeductionLog.cash_advance_request_id == request_id)
        .order_by(CashAdvanceDeductionLog.recorded_at.desc())
        .all()
    )
    return [
        {
            "id": log.id,
            "amount": float(log.amount),
            "note": log.note,
            "recorded_by_name": (
                log.recorded_by.username if log.recorded_by else None
            ),
            "recorded_at": _utc(log.recorded_at),
        }
        for log in logs
    ]


# =========================
# OPENING BALANCE (superadmin/finance) -- pre-existing balance carried
# over from before this system was used
# =========================


@router.post("/opening-balance")
def create_opening_balance(
    payload: OpeningBalanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role_or_module(roles=[], module_key="finance.cash_advance")
    ),
):
    """Records a pre-existing cash advance balance for an employee (e.g.
    carried over from a manual/paper ledger before this system existed)
    as an already-approved request, so it shows up in Outstanding
    Balances and can have deductions recorded against it exactly like
    any other request -- without inventing a separate balance concept.
    Skips the normal driver-filing flow entirely (no terms
    acknowledgement, no deduction-option/pay-period math, no approval
    routing) since this isn't a new request being filed, it's a
    superadmin recording history."""
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0.")
    if (
        payload.deduction_per_pay_amount is not None
        and payload.deduction_per_pay_amount <= 0
    ):
        raise HTTPException(
            status_code=400,
            detail="Deduction per pay period must be greater than 0.",
        )

    target_user = db.query(User).filter(User.id == payload.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found.")

    request = CashAdvanceRequest(
        user_id=target_user.id,
        employee_id=target_user.employee_id,
        requested_by_user_id=current_user.id,
        amount=payload.amount,
        deduction_option_id=None,
        # Deducted via Record Deduction over time, same as any other
        # approved request -- falls back to the full amount (a single
        # lump-sum "period") if no per-pay amount was given.
        deduction_per_pay_amount=(
            payload.deduction_per_pay_amount
            if payload.deduction_per_pay_amount is not None
            else payload.amount
        ),
        reason=payload.note.strip() if payload.note else "Opening balance",
        terms_accepted=False,
        status="approved",
        approved_amount=payload.amount,
        approved_by_user_id=current_user.id,
        approved_at=datetime.utcnow(),
    )

    db.add(request)
    db.commit()
    db.refresh(request)
    return _serialize(request, db)


@router.post("/{request_id}/release")
def set_release_info(
    request_id: int,
    payload: ReleaseInfoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role_or_module(roles=[], module_key="finance.cash_advance")
    ),
):
    """Records proof the approved funds were actually handed over to the
    employee (a GCash/bank reference, check number, etc.) -- separate
    from approval itself, since release can happen at a different time.
    Can be called again to correct/update the reference."""
    if not payload.release_reference.strip():
        raise HTTPException(
            status_code=400, detail="Reference is required."
        )

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
            detail="Release info can only be recorded for approved requests.",
        )
    _ensure_terms_settled(request)

    request.release_reference = payload.release_reference.strip()
    request.released_at = datetime.utcnow()
    request.released_by_user_id = current_user.id

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
            "created_at": _utc(alert.created_at),
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
    # true = only the archived ones (the "Show archived" toggle).
    archived: bool = False,
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
        .filter(CashAdvanceRequest.is_archived.is_(archived))
        .order_by(CashAdvanceRequest.created_at.desc())
        .all()
    )
    return [_serialize(r, db) for r in requests]


_require_finance = require_role_or_module(roles=[], module_key="finance.cash_advance")


def _get_request(db: Session, request_id: int) -> CashAdvanceRequest:
    request = db.query(CashAdvanceRequest).filter(CashAdvanceRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Cash advance request not found")
    return request


@router.post("/{request_id}/archive")
def archive_cash_advance_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_finance),
):
    """Hide a finished request from All Requests (still counted in
    balances / payroll deductions)."""
    request = _get_request(db, request_id)
    if request.status == "pending":
        raise HTTPException(
            status_code=400,
            detail="Approve or reject it first -- pending requests can't be archived.",
        )
    request.is_archived = True
    request.archived_at = datetime.utcnow()
    request.archived_by_user_id = current_user.id
    db.commit()
    db.refresh(request)
    return _serialize(request, db)


@router.post("/{request_id}/unarchive")
def unarchive_cash_advance_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_finance),
):
    request = _get_request(db, request_id)
    request.is_archived = False
    request.archived_at = None
    request.archived_by_user_id = None
    db.commit()
    db.refresh(request)
    return _serialize(request, db)


@router.post("/{request_id}/receipt")
def upload_release_receipt(
    request_id: int,
    receipt: UploadFile = File(...),
    release_reference: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Photo proving the approved cash advance was sent (GCash / bank
    screenshot, signed voucher). Marks it released. Allowed for whoever
    gave the final approval, a superadmin, or a Cash Advance "Can edit"
    grant (Finance); uploading again replaces the shown receipt."""
    request = _get_request(db, request_id)
    if request.status != "approved":
        raise HTTPException(
            status_code=400, detail="A receipt can only be added to an approved cash advance."
        )
    _ensure_terms_settled(request)
    if request.approved_by_user_id != current_user.id and not has_editable_grant(
        db, current_user, ["finance.cash_advance"]
    ):
        raise HTTPException(status_code=403, detail="You can't add a receipt to this cash advance.")
    if not (receipt.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="The receipt must be a photo.")

    url = FileService().upload(receipt, f"cash_advance/{request.id}/receipt")
    db.add(
        FileModel(
            entity_type="cash_advance",
            entity_id=request.id,
            document_type=RECEIPT_DOC,
            file_url=url,
            uploaded_by=current_user.id,
        )
    )
    if release_reference and release_reference.strip():
        request.release_reference = release_reference.strip()[:255]
    elif not request.release_reference:
        request.release_reference = "Receipt photo"
    request.released_at = datetime.utcnow()
    request.released_by_user_id = current_user.id
    db.commit()
    db.refresh(request)
    return _serialize(request, db)

