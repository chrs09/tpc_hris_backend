# app/api/trip_expenses.py
#
# Driver trip money (Approvals -> Trip Expenses; mobile Profile -> Trip
# Expenses). Two kinds (see app/models/trip_expense.py):
#
#   budget -- money first: driver (or office) requests it for a trip ->
#     Org Chart heads with "Trip Expenses" ticked approve -> Finance
#     releases (check / cash) -> driver liquidates (actual expenses +
#     receipts) -> Finance reviews each line (allow / disallow) -> unspent
#     cash returned or deducted in payroll; overspend reimbursed in payroll.
#   report -- spent first: driver adds expenses + receipts and submits ->
#     Finance reviews -> allowed total reimbursed in payroll.
#
# Finance = anyone with Finance -> Trip Expenses (or superadmin).

import json
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role_or_module
from app.models.employees import Employee
from app.models.trip_charge import TripCharge, TripChargeAllocation
from app.models.trip_expense import TripExpense, TripExpenseLine
from app.models.trips import Trip
from app.models.user import User
from app.models.vehicle_unit import VehicleUnit
from app.services.approval_chain import (
    acting_index,
    append_log,
    describe_chain,
    dump_chain,
    load_json_list,
    log_skipped,
    resolve_chain,
    skipped_for,
)
from app.services.file_service import FileService
from app.services.payroll_lock import ensure_unlocked
from app.services.payroll_scope import allowed_employee_ids
from app.utils.timezone import utc_to_ph
from app.utils.user_display import display_name

router = APIRouter(prefix="/trip-expenses", tags=["Trip Expenses"])

_require_finance = require_role_or_module(roles=["admin"], module_key="finance.trip_expenses")
_require_payroll = require_role_or_module(roles=["admin"], module_key="payroll.payroll")

CATEGORIES = {
    "shipping": "Shipping / vessel",
    "port": "Port fees",
    "toll": "Toll",
    "parking": "Parking",
    "fuel": "Fuel",
    "food": "Meals",
    "lodging": "Lodging",
    "parts": "Parts",
    "repair": "Repair / labor",
    "other": "Other",
}
CANCELLABLE = ("pending_approval", "for_release", "draft")
EDITABLE = ("released", "returned", "draft")
CENT = Decimal("0.01")


def _money(value) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except Exception:
        raise HTTPException(status_code=400, detail="Enter valid amounts.")


def _today_ph() -> date:
    return utc_to_ph(datetime.utcnow()).date()


def _fmt(dt):
    return utc_to_ph(dt).strftime("%b %d, %Y %I:%M %p") if dt else None


def _role(user: User) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role)


def _is_superadmin(user: User) -> bool:
    return _role(user) == "superadmin"


def _is_finance(request: Request, db: Session, user: User) -> bool:
    try:
        _require_finance(request=request, current_user=user, db=db)
        return True
    except HTTPException:
        return False


def _log(expense: TripExpense, action: str, user: User, note: str | None = None) -> None:
    entries = load_json_list(expense.history)
    entries.append(
        {
            "action": action,
            "by": display_name(user),
            "at": datetime.now(timezone.utc).isoformat(),
            "note": note,
        }
    )
    expense.history = json.dumps(entries)


def _query(db: Session):
    return db.query(TripExpense).options(
        joinedload(TripExpense.employee),
        joinedload(TripExpense.lines),
        joinedload(TripExpense.trip),
        joinedload(TripExpense.filed_by),
        joinedload(TripExpense.released_by),
        joinedload(TripExpense.reviewed_by),
    )


def _get(db: Session, expense_id: int) -> TripExpense:
    expense = _query(db).filter(TripExpense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Trip expense not found.")
    return expense


def _line(line: TripExpenseLine) -> dict:
    return {
        "id": line.id,
        "stage": line.stage,
        "category": line.category,
        "category_label": CATEGORIES.get(line.category, line.category),
        "description": line.description,
        "amount": float(line.amount or 0),
        "expense_date": line.expense_date.isoformat() if line.expense_date else None,
        "receipt_url": line.receipt_url,
        "allowed_amount": float(line.allowed_amount) if line.allowed_amount is not None else None,
        "review_note": line.review_note,
    }


def _serialize(db: Session, expense: TripExpense, viewer: User | None = None) -> dict:
    requested = [l for l in expense.lines if l.stage == "request"]
    actual = [l for l in expense.lines if l.stage == "actual"]
    unit = db.get(VehicleUnit, expense.vehicle_unit_id) if expense.vehicle_unit_id else None
    trip = expense.trip
    chain_info = (
        describe_chain(
            db,
            expense.approval_chain,
            expense.approval_step,
            expense.approval_log,
            expense.status != "pending_approval",
        )
        if expense.approval_chain
        else {"approval_steps": [], "approval_log": load_json_list(expense.approval_log)}
    )
    emp = expense.employee
    return {
        "id": expense.id,
        "kind": expense.kind,
        "status": expense.status,
        "employee_id": expense.employee_id,
        "employee_name": " ".join(f"{emp.first_name or ''} {emp.last_name or ''}".split()) if emp else None,
        "filed_by": display_name(expense.filed_by) if expense.filed_by else None,
        "trip_id": expense.trip_id,
        "trip_label": (
            " · ".join(
                filter(
                    None,
                    [
                        trip.ticket_no,
                        utc_to_ph(trip.start_time).strftime("%b %d, %Y") if trip.start_time else None,
                        trip.destination_store.name if trip.destination_store else None,
                    ],
                )
            )
            if trip
            else None
        ),
        "vehicle_unit_id": expense.vehicle_unit_id,
        "vehicle_unit_label": (unit.plate_number or unit.unit_code) if unit else None,
        "purpose": expense.purpose,
        "request_lines": [_line(l) for l in requested],
        "requested_total": float(sum(_money(l.amount) for l in requested)),
        "actual_lines": [_line(l) for l in actual],
        "actual_total": float(sum(_money(l.amount) for l in actual)),
        "released_amount": float(expense.released_amount) if expense.released_amount is not None else None,
        "release_method": expense.release_method,
        "release_reference": expense.release_reference,
        "release_photo_url": expense.release_photo_url,
        "released_at": _fmt(expense.released_at),
        "released_by": display_name(expense.released_by) if expense.released_by else None,
        "submitted_at": _fmt(expense.submitted_at),
        "reviewed_at": _fmt(expense.reviewed_at),
        "reviewed_by": display_name(expense.reviewed_by) if expense.reviewed_by else None,
        "review_note": expense.review_note,
        "allowed_total": float(expense.allowed_total) if expense.allowed_total is not None else None,
        "short_amount": float(expense.short_amount) if expense.short_amount is not None else None,
        "short_settlement": expense.short_settlement,
        "reimburse_amount": float(expense.reimburse_amount) if expense.reimburse_amount is not None else None,
        "reimburse_payroll_date": (
            expense.reimburse_payroll_date.isoformat() if expense.reimburse_payroll_date else None
        ),
        "note": expense.note,
        "history": load_json_list(expense.history),
        "created_at": _fmt(expense.created_at),
        "can_act": getattr(expense, "_can_act", True),
        "viewer_away": getattr(expense, "_away", None),
        **chain_info,
    }


def _employee_of(db: Session, user: User) -> Employee:
    employee = db.get(Employee, user.employee_id) if user.employee_id else None
    if not employee:
        raise HTTPException(status_code=400, detail="Your account isn't linked to an employee.")
    return employee


def _ensure_owner_or_finance(request: Request, db: Session, expense: TripExpense, user: User):
    if user.employee_id and user.employee_id == expense.employee_id:
        return
    if not _is_finance(request, db, user):
        raise HTTPException(status_code=404, detail="Trip expense not found.")


def _clean_lines(lines: list, stage: str) -> list[TripExpenseLine]:
    out = []
    for i, raw in enumerate(lines, start=1):
        category = (raw.get("category") or "").strip().lower()
        if category not in CATEGORIES:
            raise HTTPException(status_code=400, detail=f"Line {i}: pick a category.")
        amount = _money(raw.get("amount"))
        if amount <= 0:
            raise HTTPException(status_code=400, detail=f"Line {i}: enter an amount above 0.")
        expense_date = raw.get("expense_date")
        try:
            expense_date = date.fromisoformat(expense_date) if expense_date else None
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Line {i}: use a date like 2026-11-06.")
        out.append(
            TripExpenseLine(
                id=raw.get("id") or None,
                stage=stage,
                category=category,
                description=(raw.get("description") or "").strip()[:500] or None,
                amount=amount,
                expense_date=expense_date,
            )
        )
    return out


def _require_file(upload: UploadFile, label: str):
    if upload is None or not upload.filename:
        raise HTTPException(status_code=400, detail=f"{label} is required.")
    kind = upload.content_type or ""
    if not (kind.startswith("image/") or kind == "application/pdf"):
        raise HTTPException(status_code=400, detail=f"{label} must be a photo or PDF.")


# =====================================================================
# LOOKUPS
# =====================================================================
@router.get("/categories")
def list_categories(current_user: User = Depends(get_current_user)):
    return [{"value": k, "label": v} for k, v in CATEGORIES.items()]


@router.get("/trips")
def list_trips_for_expense(
    request: Request,
    employee_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The driver's recent trips (newest first) to link a budget / report
    to -- their own, or (Finance) any driver's."""
    if employee_id and employee_id != current_user.employee_id:
        if not _is_finance(request, db, current_user):
            raise HTTPException(status_code=403, detail="Not allowed.")
        driver = db.query(User).filter(User.employee_id == employee_id).first()
    else:
        driver = current_user
    if not driver:
        return []
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.destination_store))
        .filter(Trip.driver_id == driver.id, Trip.is_archived.is_(False))
        .order_by(Trip.start_time.desc())
        .limit(60)
        .all()
    )
    return [
        {
            "id": t.id,
            "label": " · ".join(
                filter(
                    None,
                    [
                        t.ticket_no or t.trip_code or f"Trip #{t.id}",
                        utc_to_ph(t.start_time).strftime("%b %d, %Y") if t.start_time else None,
                        t.destination_store.name if t.destination_store else None,
                    ],
                )
            ),
            "vehicle_unit_id": t.vehicle_unit_id,
        }
        for t in trips
    ]


# =====================================================================
# FILING (driver, or Finance for a driver)
# =====================================================================
class ExpenseIn(BaseModel):
    kind: str
    employee_id: int | None = None
    trip_id: int | None = None
    vehicle_unit_id: int | None = None
    purpose: str | None = None
    lines: list[dict] = []


@router.post("")
def file_trip_expense(
    payload: ExpenseIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.kind not in ("budget", "report"):
        raise HTTPException(status_code=400, detail="Pick a trip budget or an expense report.")
    if payload.employee_id and payload.employee_id != current_user.employee_id:
        if not _is_finance(request, db, current_user):
            raise HTTPException(status_code=403, detail="You can only file your own.")
        employee = db.get(Employee, payload.employee_id)
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found.")
        driver_user = db.query(User).filter(User.employee_id == employee.id).first()
    else:
        employee = _employee_of(db, current_user)
        driver_user = current_user

    trip = db.get(Trip, payload.trip_id) if payload.trip_id else None
    if payload.trip_id and not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    if payload.kind == "budget" and not trip:
        raise HTTPException(status_code=400, detail="Pick the trip this budget is for.")
    if payload.vehicle_unit_id and not db.get(VehicleUnit, payload.vehicle_unit_id):
        raise HTTPException(status_code=404, detail="Vehicle unit not found.")
    if not payload.lines:
        raise HTTPException(
            status_code=400,
            detail="Add at least one item." if payload.kind == "budget" else "Add at least one expense.",
        )

    stage = "request" if payload.kind == "budget" else "actual"
    chain = (
        resolve_chain(db, employee, driver_user, "trip_expense") if payload.kind == "budget" else []
    )
    expense = TripExpense(
        kind=payload.kind,
        status=("pending_approval" if chain else "for_release") if payload.kind == "budget" else "draft",
        employee_id=employee.id,
        user_id=driver_user.id if driver_user else None,
        filed_by_user_id=current_user.id,
        trip_id=trip.id if trip else None,
        vehicle_unit_id=payload.vehicle_unit_id or (trip.vehicle_unit_id if trip else None),
        purpose=(payload.purpose or "").strip()[:2000] or None,
        approval_chain=dump_chain(chain),
        approval_step=0,
    )
    for line in _clean_lines(payload.lines, stage):
        line.id = None
        expense.lines.append(line)
    _log(expense, "filed", current_user)
    db.add(expense)
    db.commit()
    return _serialize(db, _get(db, expense.id), current_user)


@router.get("/mine")
def list_my_trip_expenses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.employee_id:
        return []
    rows = (
        _query(db)
        .filter(TripExpense.employee_id == current_user.employee_id)
        .order_by(TripExpense.created_at.desc())
        .limit(100)
        .all()
    )
    return [_serialize(db, r, current_user) for r in rows]


@router.get("/{expense_id}")
def get_trip_expense(
    expense_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = _get(db, expense_id)
    chain = [int(i) for i in load_json_list(expense.approval_chain)]
    if current_user.id not in chain:
        _ensure_owner_or_finance(request, db, expense, current_user)
    return _serialize(db, expense, current_user)


@router.put("/{expense_id}/actual-lines")
def save_actual_lines(
    expense_id: int,
    request: Request,
    lines: list[dict] = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The liquidation (budget) or the report's expenses: replaces the
    actual lines; lines kept (same id) keep their receipt."""
    expense = _get(db, expense_id)
    _ensure_owner_or_finance(request, db, expense, current_user)
    if expense.status not in EDITABLE:
        raise HTTPException(status_code=400, detail="This can't be changed now.")
    keep = {l.id: l for l in expense.lines if l.stage == "actual"}
    cleaned = _clean_lines(lines, "actual")
    kept_ids = set()
    for line in cleaned:
        old = keep.get(line.id)
        if old is not None:
            old.category, old.description = line.category, line.description
            old.amount, old.expense_date = line.amount, line.expense_date
            kept_ids.add(old.id)
        else:
            line.id = None
            expense.lines.append(line)
    for line_id, old in keep.items():
        if line_id not in kept_ids:
            expense.lines.remove(old)
    db.commit()
    return _serialize(db, _get(db, expense.id), current_user)


@router.post("/{expense_id}/lines/{line_id}/receipt")
def upload_line_receipt(
    expense_id: int,
    line_id: int,
    request: Request,
    receipt: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = _get(db, expense_id)
    _ensure_owner_or_finance(request, db, expense, current_user)
    if expense.status not in EDITABLE:
        raise HTTPException(status_code=400, detail="This can't be changed now.")
    line = next((l for l in expense.lines if l.id == line_id and l.stage == "actual"), None)
    if not line:
        raise HTTPException(status_code=404, detail="Expense line not found.")
    _require_file(receipt, "Receipt")
    line.receipt_url = FileService().upload(receipt, f"trip_expenses/{expense.id}/receipts")
    db.commit()
    return _serialize(db, _get(db, expense.id), current_user)


@router.post("/{expense_id}/submit")
def submit_for_review(
    expense_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liquidation / report done -> Finance reviews it."""
    expense = _get(db, expense_id)
    _ensure_owner_or_finance(request, db, expense, current_user)
    if expense.status not in EDITABLE:
        raise HTTPException(status_code=400, detail="This can't be submitted now.")
    actual = [l for l in expense.lines if l.stage == "actual"]
    if expense.kind == "report" and not actual:
        raise HTTPException(status_code=400, detail="Add at least one expense.")
    expense.status = "for_review"
    expense.submitted_at = datetime.utcnow()
    expense.note = None
    _log(expense, "submitted", current_user)
    db.commit()
    return _serialize(db, _get(db, expense.id), current_user)


@router.post("/{expense_id}/cancel")
def cancel_trip_expense(
    expense_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = _get(db, expense_id)
    _ensure_owner_or_finance(request, db, expense, current_user)
    if expense.status not in CANCELLABLE:
        raise HTTPException(
            status_code=400, detail="Only a request not yet released / submitted can be cancelled."
        )
    expense.status = "cancelled"
    _log(expense, "cancelled", current_user)
    db.commit()
    return _serialize(db, _get(db, expense.id), current_user)


# =====================================================================
# ORG CHART HEADS -- approve a budget before Finance releases it
# =====================================================================
@router.get("/approvals/for-me")
def list_for_my_approval(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        _query(db)
        .filter(TripExpense.status == "pending_approval")
        .order_by(TripExpense.created_at.asc())
        .all()
    )
    if _is_superadmin(current_user):
        return [_serialize(db, r, current_user) for r in rows]
    mine = []
    for expense in rows:
        chain = [int(i) for i in load_json_list(expense.approval_chain)]
        if acting_index(db, chain, expense.approval_step, current_user.id)[0] is not None:
            expense._can_act = True
            mine.append(expense)
        else:
            away = skipped_for(db, chain, expense.approval_step, current_user.id)
            if away:
                expense._can_act = False
                expense._away = away
                mine.append(expense)
    return [_serialize(db, r, current_user) for r in mine]


def _approval_turn(db: Session, expense: TripExpense, user: User):
    if expense.status != "pending_approval":
        raise HTTPException(status_code=400, detail="This request isn't waiting for approval.")
    chain = [int(i) for i in load_json_list(expense.approval_chain)]
    acting, skipped = acting_index(db, chain, expense.approval_step, user.id)
    if acting is None and not _is_superadmin(user):
        raise HTTPException(status_code=403, detail="It isn't your turn to approve this request.")
    return chain, acting, skipped


@router.post("/{expense_id}/approve")
def approve_budget(
    expense_id: int,
    remarks: str | None = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = _get(db, expense_id)
    chain, acting, skipped = _approval_turn(db, expense, current_user)
    expense.approval_log = log_skipped(db, expense.approval_log, chain, skipped)
    expense.approval_log = append_log(expense.approval_log, current_user, "approved", remarks)
    if acting is not None and acting < len(chain) - 1:
        expense.approval_step = acting + 1
    else:
        expense.approval_step = len(chain)
        expense.status = "for_release"
    db.commit()
    return _serialize(db, _get(db, expense.id), current_user)


@router.post("/{expense_id}/reject")
def reject_trip_expense(
    expense_id: int,
    request: Request,
    reason: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A head rejects a budget awaiting approval; Finance can reject a
    budget not yet released, or a report under review."""
    expense = _get(db, expense_id)
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required.")
    if expense.status == "pending_approval":
        chain, _acting, skipped = _approval_turn(db, expense, current_user)
        expense.approval_log = log_skipped(db, expense.approval_log, chain, skipped)
        expense.approval_log = append_log(expense.approval_log, current_user, "rejected", reason)
    elif expense.status in ("for_release",) or (
        expense.kind == "report" and expense.status == "for_review"
    ):
        if not _is_finance(request, db, current_user):
            raise HTTPException(status_code=403, detail="Not allowed.")
    else:
        raise HTTPException(status_code=400, detail="This can't be rejected now.")
    expense.status = "rejected"
    expense.note = reason[:2000]
    _log(expense, "rejected", current_user, reason)
    db.commit()
    return _serialize(db, _get(db, expense.id), current_user)


# =====================================================================
# FINANCE -- release, review
# =====================================================================
@router.get("")
def list_trip_expenses(
    status: str | None = None,
    kind: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_finance),
):
    """status: one status, "needs_action" (for release + for review), or
    all. Newest first."""
    q = _query(db)
    if status == "needs_action":
        q = q.filter(TripExpense.status.in_(("for_release", "for_review")))
    elif status == "open":
        q = q.filter(TripExpense.status.notin_(("completed", "rejected", "cancelled")))
    elif status:
        q = q.filter(TripExpense.status == status)
    if kind:
        q = q.filter(TripExpense.kind == kind)
    rows = q.order_by(TripExpense.updated_at.desc()).limit(300).all()
    return [_serialize(db, r, current_user) for r in rows]


@router.post("/{expense_id}/release")
def release_budget(
    expense_id: int,
    amount: float = Form(...),
    method: str = Form(...),
    reference: str | None = Form(None),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_finance),
):
    expense = _get(db, expense_id)
    if expense.kind != "budget" or expense.status != "for_release":
        raise HTTPException(status_code=400, detail="This budget isn't waiting for release.")
    if method not in ("check", "cash"):
        raise HTTPException(status_code=400, detail="Pick check or cash.")
    released = _money(amount)
    if released <= 0:
        raise HTTPException(status_code=400, detail="Enter the amount released.")
    if photo is not None and photo.filename:
        _require_file(photo, "Release photo")
        expense.release_photo_url = FileService().upload(photo, f"trip_expenses/{expense.id}/release")
    expense.released_amount = released
    expense.release_method = method
    expense.release_reference = (reference or "").strip()[:100] or None
    expense.released_at = datetime.utcnow()
    expense.released_by_user_id = current_user.id
    expense.status = "released"
    _log(expense, "released", current_user, f"{method} ₱{released:,.2f}")
    db.commit()
    return _serialize(db, _get(db, expense.id), current_user)


@router.post("/{expense_id}/return")
def return_for_correction(
    expense_id: int,
    reason: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_finance),
):
    expense = _get(db, expense_id)
    if expense.status != "for_review":
        raise HTTPException(status_code=400, detail="Only something under review can be returned.")
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Say what needs fixing.")
    expense.status = "returned"
    expense.note = reason[:2000]
    _log(expense, "returned", current_user, reason)
    db.commit()
    return _serialize(db, _get(db, expense.id), current_user)


class ReviewIn(BaseModel):
    # Each actual line: allowed amount (0 = disallowed) and why.
    lines: list[dict]
    # Budget, unspent cash: "returned_cash" or "payroll".
    short_settlement: str | None = None
    # Payroll deduction per pay (null = all at once).
    deduction_per_pay: float | None = None
    # Reimbursement paid with the payroll covering this date.
    payroll_date: str | None = None
    note: str | None = None


@router.post("/{expense_id}/review")
def review_and_settle(
    expense_id: int,
    payload: ReviewIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_finance),
):
    expense = _get(db, expense_id)
    if expense.status != "for_review":
        raise HTTPException(status_code=400, detail="This isn't waiting for review.")
    actual = {l.id: l for l in expense.lines if l.stage == "actual"}
    given = {int(row.get("id") or 0): row for row in payload.lines}
    for line_id, line in actual.items():
        row = given.get(line_id)
        if row is None:
            raise HTTPException(status_code=400, detail="Review every expense line.")
        allowed = _money(row.get("allowed_amount"))
        if allowed < 0 or allowed > _money(line.amount):
            raise HTTPException(
                status_code=400,
                detail="An allowed amount must be between 0 and what was spent.",
            )
        note = (row.get("review_note") or "").strip()
        if allowed < _money(line.amount) and not note:
            raise HTTPException(
                status_code=400, detail="Give a reason for each line not fully allowed."
            )
        line.allowed_amount = allowed
        line.review_note = note[:500] or None
    allowed_total = sum((_money(l.allowed_amount) for l in actual.values()), Decimal("0"))

    short = Decimal("0")
    reimburse = allowed_total
    if expense.kind == "budget":
        diff = _money(expense.released_amount) - allowed_total
        short = diff if diff > 0 else Decimal("0")
        reimburse = -diff if diff < 0 else Decimal("0")

    payroll_day = None
    if reimburse > 0:
        try:
            payroll_day = (
                date.fromisoformat(payload.payroll_date) if payload.payroll_date else _today_ph()
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Use a date like 2026-11-15.")
        # Not into a payroll that's already locked.
        ensure_unlocked(db, expense.employee_id, payroll_day, "a reimbursement")

    if short > 0:
        if payload.short_settlement not in ("returned_cash", "payroll"):
            raise HTTPException(
                status_code=400,
                detail="Unspent cash: pick returned in cash, or deduct from payroll.",
            )
        per_pay = None
        if payload.short_settlement == "payroll" and payload.deduction_per_pay:
            per_pay = _money(payload.deduction_per_pay)
            if per_pay <= 0:
                raise HTTPException(status_code=400, detail="Enter a valid amount per pay.")
        if payload.short_settlement == "payroll":
            if not expense.trip_id:
                raise HTTPException(status_code=400, detail="This budget has no trip.")
            charge = TripCharge(
                charge_type="liquidation",
                status="approved",
                trip_id=expense.trip_id,
                incident_date=_today_ph(),
                description=f"Unspent trip budget (Trip Expenses #{expense.id})",
                total_amount=short,
                chargeable_amount=short,
                chargeable_reason="Trip budget liquidation",
                created_by_user_id=current_user.id,
                approved_by_user_id=current_user.id,
                approved_at=datetime.utcnow(),
                history=json.dumps(
                    [{
                        "action": "approved",
                        "by": current_user.id,
                        "by_name": display_name(current_user),
                        "at": datetime.now(timezone.utc).isoformat(),
                        "note": f"From Trip Expenses #{expense.id}",
                    }]
                ),
            )
            charge.allocations.append(
                TripChargeAllocation(
                    employee_id=expense.employee_id, amount=short, deduction_per_pay=per_pay
                )
            )
            db.add(charge)
            db.flush()
            expense.trip_charge_id = charge.id
        expense.short_settlement = payload.short_settlement

    expense.allowed_total = allowed_total
    expense.short_amount = short if short > 0 else None
    expense.reimburse_amount = reimburse if reimburse > 0 else None
    expense.reimburse_payroll_date = payroll_day
    expense.review_note = (payload.note or "").strip()[:2000] or None
    expense.reviewed_at = datetime.utcnow()
    expense.reviewed_by_user_id = current_user.id
    expense.status = "completed"
    summary = f"allowed ₱{allowed_total:,.2f}"
    if short > 0:
        summary += f"; unspent ₱{short:,.2f} ({payload.short_settlement.replace('_', ' ')})"
    if reimburse > 0:
        summary += f"; reimburse ₱{reimburse:,.2f} with payroll of {payroll_day}"
    _log(expense, "reviewed", current_user, summary)
    db.commit()
    return _serialize(db, _get(db, expense.id), current_user)


# =====================================================================
# PAYROLL -- reimbursements paid with a cutoff
# =====================================================================
@router.get("/payroll/reimbursements")
def reimbursements_for_payroll(
    start: date,
    end: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    """{employee_id: {"total", "lines": [{id, kind, label, amount}]}} --
    reimbursements whose payroll date falls in start..end. Shown on the
    payroll as a line after net pay (like incentives), not part of gross."""
    rows = (
        _query(db)
        .filter(
            TripExpense.status == "completed",
            TripExpense.reimburse_amount.isnot(None),
            TripExpense.reimburse_payroll_date >= start,
            TripExpense.reimburse_payroll_date <= end,
        )
        .all()
    )
    allowed = allowed_employee_ids(db, current_user)
    result = {}
    for expense in rows:
        if allowed is not None and expense.employee_id not in allowed:
            continue
        entry = result.setdefault(str(expense.employee_id), {"total": 0, "lines": []})
        amount = float(expense.reimburse_amount or 0)
        entry["lines"].append(
            {
                "id": expense.id,
                "kind": expense.kind,
                "label": (
                    f"Trip budget overspend #{expense.id}"
                    if expense.kind == "budget"
                    else f"Expense report #{expense.id}"
                ),
                "amount": amount,
            }
        )
        entry["total"] = round(entry["total"] + amount, 2)
    return result
