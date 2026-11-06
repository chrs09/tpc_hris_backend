# app/api/admin/trip_charges.py
#
# Trip Management -> Trip Charges: shortages and accidents on a trip, who
# pays what, and (once approved) deductions through payroll -- see
# app/services/trip_charge_payroll.py.

import json
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import has_editable_grant, require_role_or_module
from app.models.employees import Employee
from app.models.trip_charge import TripCharge, TripChargeAllocation
from app.models.trips import Trip, TripStatus
from app.models.user import User
from app.services.file_service import FileService
from app.utils.user_display import display_name

router = APIRouter(prefix="/admin/trip-charges", tags=["Trip Charges"])

_require_access = require_role_or_module(
    roles=["coordinator_admin", "office_admin"],
    module_key="trip_management.trip_charges",
)

# Approving is its own tick on the Org Chart (or superadmin).
APPROVE_MODULE = "trip_management.trip_charges_approve"

CENT = Decimal("0.01")
INSURANCE_STATUSES = ("pending", "covered", "denied", "not_claimed")
INVESTIGATION_RESULTS = ("pending", "negligent", "not_negligent")


class AllocationIn(BaseModel):
    employee_id: int
    amount: float
    deduction_per_pay: float | None = None


class ChargeIn(BaseModel):
    charge_type: str
    trip_id: int
    incident_date: date
    description: str | None = None
    total_amount: float
    shipment_no: str | None = None
    report_reference: str | None = None
    report_date: date | None = None
    item: str | None = None
    quantity: float | None = None
    unit_cost: float | None = None
    insurance_status: str | None = None
    insurance_reference: str | None = None
    participation_amount: float | None = None
    investigation_result: str | None = None
    investigation_notes: str | None = None
    chargeable_amount: float
    chargeable_reason: str | None = None
    allocations: list[AllocationIn] = []


class ReviseIn(ChargeIn):
    reason: str


class ExplanationIn(BaseModel):
    explanation: str


class ReasonIn(BaseModel):
    reason: str


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _utc(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def _json_list(value) -> list:
    try:
        data = json.loads(value) if value else []
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def _log(charge: TripCharge, action: str, user: User, note: str | None = None) -> None:
    entries = _json_list(charge.history)
    entries.append(
        {
            "action": action,
            "by": user.id,
            "by_name": display_name(user),
            "at": datetime.now(timezone.utc).isoformat(),
            "note": note,
        }
    )
    charge.history = json.dumps(entries)


def suggested_chargeable(
    charge_type: str,
    total,
    insurance_status: str | None,
    participation,
    investigation_result: str | None,
) -> Decimal | None:
    """What personnel pay under the ticket's rules; None = can't tell yet.
    Covered stays the participation even with negligence, since that's all
    the company actually lost."""
    total = _money(total)
    if charge_type == "shortage":
        return total
    if insurance_status == "covered":
        return min(_money(participation), total)
    if insurance_status == "denied":
        return total
    if insurance_status == "not_claimed" and investigation_result != "pending":
        return total if investigation_result == "negligent" else Decimal("0")
    return None


def _deducted(allocation: TripChargeAllocation) -> Decimal:
    return sum((_money(log.amount) for log in allocation.deduction_logs), Decimal("0"))


def _employee_name(employee: Employee | None) -> str:
    return f"{employee.first_name} {employee.last_name}" if employee else "Unknown"


def _serialize(charge: TripCharge) -> dict:
    allocations = []
    settled = charge.status == "approved"
    for allocation in charge.allocations:
        amount = _money(allocation.amount)
        deducted = _deducted(allocation)
        balance = max(amount - deducted, Decimal("0"))
        if balance > 0:
            settled = False
        allocations.append(
            {
                "id": allocation.id,
                "employee_id": allocation.employee_id,
                "employee_name": _employee_name(allocation.employee),
                "amount": float(amount),
                "deduction_per_pay": (
                    float(allocation.deduction_per_pay)
                    if allocation.deduction_per_pay is not None
                    else None
                ),
                "deducted": float(deducted),
                "balance": float(balance),
                # A revision can lower the share below what was already taken.
                "refund_due": float(max(deducted - amount, Decimal("0"))),
                "notified_at": _utc(allocation.notified_at),
                "explanation": allocation.explanation,
            }
        )

    total = _money(charge.total_amount)
    chargeable = _money(charge.chargeable_amount)
    insurer = Decimal("0")
    if charge.charge_type == "accident" and charge.insurance_status == "covered":
        insurer = max(total - _money(charge.participation_amount), Decimal("0"))
    trip = charge.trip
    return {
        "id": charge.id,
        "charge_type": charge.charge_type,
        "status": charge.status,
        "display_status": "settled" if settled else charge.status,
        "trip_id": charge.trip_id,
        "trip": _trip_summary(trip) if trip else None,
        "incident_date": charge.incident_date.isoformat() if charge.incident_date else None,
        "description": charge.description,
        "total_amount": float(total),
        "shipment_no": charge.shipment_no,
        "report_reference": charge.report_reference,
        "report_date": charge.report_date.isoformat() if charge.report_date else None,
        "item": charge.item,
        "quantity": float(charge.quantity) if charge.quantity is not None else None,
        "unit_cost": float(charge.unit_cost) if charge.unit_cost is not None else None,
        "insurance_status": charge.insurance_status,
        "insurance_reference": charge.insurance_reference,
        "participation_amount": (
            float(charge.participation_amount)
            if charge.participation_amount is not None
            else None
        ),
        "investigation_result": charge.investigation_result,
        "investigation_notes": charge.investigation_notes,
        "chargeable_amount": float(chargeable),
        "chargeable_reason": charge.chargeable_reason,
        "insurer_amount": float(insurer),
        "company_amount": float(max(total - insurer - chargeable, Decimal("0"))),
        "allocations": allocations,
        "attachments": _json_list(charge.attachments),
        "history": _json_list(charge.history),
        "created_by_name": display_name(charge.created_by) if charge.created_by else None,
        "created_at": _utc(charge.created_at),
        "approved_by_name": display_name(charge.approved_by) if charge.approved_by else None,
        "approved_at": _utc(charge.approved_at),
    }


def _trip_summary(trip: Trip) -> dict:
    driver = trip.driver
    crew = []
    if driver and driver.employee:
        crew.append(
            {
                "employee_id": driver.employee.id,
                "name": _employee_name(driver.employee),
                "role": "Driver",
            }
        )
    for helper in trip.helpers:
        crew.append(
            {"employee_id": helper.id, "name": _employee_name(helper), "role": "Helper"}
        )
    return {
        "id": trip.id,
        "trip_code": trip.trip_code,
        "shipment_no": trip.ticket_no,
        "date": trip.start_time.date().isoformat() if trip.start_time else None,
        "origin": trip.origin_store.name if trip.origin_store else None,
        "destination": trip.destination_store.name if trip.destination_store else None,
        "vehicle": (
            " - ".join(
                dict.fromkeys(
                    filter(None, [trip.vehicle_unit.unit_code, trip.vehicle_unit.plate_number])
                )
            )
            if trip.vehicle_unit
            else None
        ),
        "crew": crew,
    }


def _validate(db: Session, payload: ChargeIn) -> None:
    if payload.charge_type not in ("shortage", "accident"):
        raise HTTPException(status_code=400, detail="Choose shortage or accident.")
    if not db.query(Trip.id).filter(Trip.id == payload.trip_id).first():
        raise HTTPException(status_code=404, detail="Trip not found.")
    if payload.total_amount <= 0:
        raise HTTPException(status_code=400, detail="Enter an amount greater than zero.")
    if payload.chargeable_amount < 0 or _money(payload.chargeable_amount) > _money(
        payload.total_amount
    ):
        raise HTTPException(
            status_code=400,
            detail="The amount charged to personnel can't be more than the total.",
        )

    if payload.charge_type == "accident":
        if (payload.insurance_status or "pending") not in INSURANCE_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid insurance result.")
        if (payload.investigation_result or "pending") not in INVESTIGATION_RESULTS:
            raise HTTPException(status_code=400, detail="Invalid investigation result.")
        if payload.insurance_status == "covered" and not payload.participation_amount:
            raise HTTPException(
                status_code=400, detail="Enter the participation amount."
            )

    rule = suggested_chargeable(
        payload.charge_type,
        payload.total_amount,
        payload.insurance_status or "pending",
        payload.participation_amount,
        payload.investigation_result or "pending",
    )
    if (
        rule is not None
        and rule != _money(payload.chargeable_amount)
        and not (payload.chargeable_reason or "").strip()
    ):
        raise HTTPException(
            status_code=400,
            detail=f"The usual charge is ₱{rule:,.2f}. Give a reason for a different amount.",
        )

    ids = [row.employee_id for row in payload.allocations]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Each person can only be listed once.")
    if ids:
        found = db.query(Employee.id).filter(Employee.id.in_(ids)).count()
        if found != len(ids):
            raise HTTPException(status_code=400, detail="Employee not found.")
    for row in payload.allocations:
        if row.amount < 0:
            raise HTTPException(status_code=400, detail="A share can't be negative.")
        if row.deduction_per_pay is not None and row.deduction_per_pay <= 0:
            raise HTTPException(
                status_code=400, detail="The per-cutoff amount must be more than zero."
            )


def _ensure_shares_add_up(charge: TripCharge) -> None:
    total = sum((_money(a.amount) for a in charge.allocations), Decimal("0"))
    chargeable = _money(charge.chargeable_amount)
    if total != chargeable:
        raise HTTPException(
            status_code=400,
            detail=f"Shares add up to ₱{total:,.2f} but the charge is ₱{chargeable:,.2f}.",
        )


def _apply_fields(charge: TripCharge, payload: ChargeIn) -> None:
    is_shortage = payload.charge_type == "shortage"
    charge.charge_type = payload.charge_type
    charge.trip_id = payload.trip_id
    charge.incident_date = payload.incident_date
    charge.description = (payload.description or "").strip() or None
    charge.total_amount = _money(payload.total_amount)
    charge.chargeable_amount = _money(payload.chargeable_amount)
    charge.chargeable_reason = (payload.chargeable_reason or "").strip() or None
    charge.shipment_no = payload.shipment_no if is_shortage else None
    charge.report_reference = payload.report_reference if is_shortage else None
    charge.report_date = payload.report_date if is_shortage else None
    charge.item = payload.item if is_shortage else None
    charge.quantity = payload.quantity if is_shortage else None
    charge.unit_cost = payload.unit_cost if is_shortage else None
    charge.insurance_status = None if is_shortage else payload.insurance_status or "pending"
    charge.insurance_reference = None if is_shortage else payload.insurance_reference
    charge.participation_amount = None if is_shortage else payload.participation_amount
    charge.investigation_result = (
        None if is_shortage else payload.investigation_result or "pending"
    )
    charge.investigation_notes = None if is_shortage else payload.investigation_notes


def _sync_allocations(charge: TripCharge, rows: list[AllocationIn]) -> list[TripChargeAllocation]:
    """Matches people by employee. A changed share needs a new notice, so its
    notified_at is cleared. Someone removed after deductions stays at ₱0, so
    their refund still shows. Returns allocations whose share changed."""
    existing = {a.employee_id: a for a in charge.allocations}
    changed = []
    for row in rows:
        allocation = existing.pop(row.employee_id, None)
        amount = _money(row.amount)
        per_pay = _money(row.deduction_per_pay) if row.deduction_per_pay else None
        if allocation is None:
            allocation = TripChargeAllocation(
                employee_id=row.employee_id, amount=amount, deduction_per_pay=per_pay
            )
            charge.allocations.append(allocation)
            changed.append(allocation)
            continue
        if _money(allocation.amount) != amount:
            allocation.notified_at = None
            changed.append(allocation)
        allocation.amount = amount
        allocation.deduction_per_pay = per_pay
    for allocation in existing.values():
        if allocation.deduction_logs:
            allocation.amount = Decimal("0")
            changed.append(allocation)
        else:
            charge.allocations.remove(allocation)
    return changed


def _get_charge(db: Session, charge_id: int) -> TripCharge:
    charge = (
        db.query(TripCharge)
        .options(
            joinedload(TripCharge.allocations).joinedload(TripChargeAllocation.employee),
            joinedload(TripCharge.allocations).joinedload(TripChargeAllocation.deduction_logs),
        )
        .filter(TripCharge.id == charge_id)
        .first()
    )
    if not charge:
        raise HTTPException(status_code=404, detail="Charge not found.")
    return charge


def _ensure_can_approve(db: Session, user: User) -> None:
    if not has_editable_grant(db, user, [APPROVE_MODULE]):
        raise HTTPException(
            status_code=403, detail="You don't have access to approve trip charges."
        )


@router.get("/trip-lookup")
def lookup_trips(
    q: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_access),
):
    """Finds a trip by shipment number or trip code, newest first."""
    q = q.strip()
    if len(q) < 2:
        return []
    trips = (
        db.query(Trip)
        .filter(
            Trip.status != TripStatus.CANCELLED,
            or_(Trip.ticket_no.ilike(f"%{q}%"), Trip.trip_code.ilike(f"%{q}%")),
        )
        .order_by(Trip.id.desc())
        .limit(20)
        .all()
    )
    return [_trip_summary(trip) for trip in trips]


@router.get("/employees")
def list_employee_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_access),
):
    """Anyone can be made responsible, not only the trip's crew."""
    employees = db.query(Employee).order_by(Employee.first_name.asc()).all()
    return [{"id": e.id, "label": _employee_name(e)} for e in employees]


@router.get("")
def list_charges(
    charge_type: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_access),
):
    query = db.query(TripCharge).options(
        joinedload(TripCharge.allocations).joinedload(TripChargeAllocation.employee),
        joinedload(TripCharge.allocations).joinedload(TripChargeAllocation.deduction_logs),
    )
    if charge_type:
        query = query.filter(TripCharge.charge_type == charge_type)
    else:
        # Unspent trip budgets deducted in payroll are handled on Trip
        # Expenses (app/api/trip_expenses.py), not here.
        query = query.filter(TripCharge.charge_type != "liquidation")
    rows = [_serialize(c) for c in query.order_by(TripCharge.id.desc()).all()]
    if status:
        rows = [r for r in rows if r["display_status"] == status]
    return rows


@router.post("")
def create_charge(
    payload: ChargeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_access),
):
    _validate(db, payload)
    charge = TripCharge(status="recorded", created_by_user_id=current_user.id)
    _apply_fields(charge, payload)
    _sync_allocations(charge, payload.allocations)
    _log(charge, "recorded", current_user)
    db.add(charge)
    db.commit()
    return _serialize(_get_charge(db, charge.id))


@router.put("/{charge_id}")
def update_charge(
    charge_id: int,
    payload: ChargeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_access),
):
    """Before approval. A changed share goes back for a new notice."""
    charge = _get_charge(db, charge_id)
    if charge.status not in ("recorded", "for_explanation"):
        raise HTTPException(
            status_code=400, detail="Only a charge not yet approved can be edited."
        )
    _validate(db, payload)
    _apply_fields(charge, payload)
    _sync_allocations(charge, payload.allocations)
    if charge.status == "for_explanation" and any(
        a.notified_at is None for a in charge.allocations
    ):
        charge.status = "recorded"
    _log(charge, "edited", current_user)
    db.commit()
    return _serialize(_get_charge(db, charge_id))


@router.post("/{charge_id}/attachments")
def add_attachment(
    charge_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_access),
):
    charge = _get_charge(db, charge_id)
    url = FileService().upload(file, f"trip_charges/{charge_id}")
    charge.attachments = json.dumps(_json_list(charge.attachments) + [url])
    db.commit()
    return _serialize(_get_charge(db, charge_id))


@router.post("/{charge_id}/record-notice")
def record_notice(
    charge_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_access),
):
    """Records that each person was told what they're being charged, so they
    can explain before it's approved. HR tells them in person for now: no
    screen shows employees their charges yet."""
    charge = _get_charge(db, charge_id)
    if charge.status not in ("recorded", "for_explanation"):
        raise HTTPException(status_code=400, detail="This charge was already decided.")
    if charge.charge_type == "accident" and (
        charge.insurance_status == "pending" or charge.investigation_result == "pending"
    ):
        raise HTTPException(
            status_code=400,
            detail="Enter the insurance and investigation results first.",
        )
    if _money(charge.chargeable_amount) <= 0:
        raise HTTPException(
            status_code=400, detail="Nothing is charged, so no notice is needed."
        )
    _ensure_shares_add_up(charge)

    pending = [a for a in charge.allocations if a.notified_at is None]
    now = datetime.utcnow()
    for allocation in pending:
        allocation.notified_at = now
    charge.status = "for_explanation"
    _log(charge, "notice_recorded", current_user)
    db.commit()
    return _serialize(_get_charge(db, charge_id))


@router.post("/{charge_id}/allocations/{allocation_id}/explanation")
def save_explanation(
    charge_id: int,
    allocation_id: int,
    payload: ExplanationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_access),
):
    charge = _get_charge(db, charge_id)
    allocation = next((a for a in charge.allocations if a.id == allocation_id), None)
    if not allocation:
        raise HTTPException(status_code=404, detail="Person not found on this charge.")
    allocation.explanation = payload.explanation.strip() or None
    _log(charge, "explanation_saved", current_user, _employee_name(allocation.employee))
    db.commit()
    return _serialize(_get_charge(db, charge_id))


@router.post("/{charge_id}/approve")
def approve_charge(
    charge_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_access),
):
    """Starts the deductions. A charge of ₱0 (e.g. not at fault, nothing to
    pay) closes without a notice."""
    _ensure_can_approve(db, current_user)
    charge = _get_charge(db, charge_id)
    if charge.status not in ("recorded", "for_explanation"):
        raise HTTPException(status_code=400, detail="This charge was already decided.")
    if charge.charge_type == "accident" and (
        charge.insurance_status == "pending" or charge.investigation_result == "pending"
    ):
        raise HTTPException(
            status_code=400,
            detail="Enter the insurance and investigation results first.",
        )
    if _money(charge.chargeable_amount) > 0:
        _ensure_shares_add_up(charge)
        if any(a.notified_at is None for a in charge.allocations if _money(a.amount) > 0):
            raise HTTPException(
                status_code=400,
                detail="Give the notice first so each person can explain.",
            )
    charge.status = "approved"
    charge.approved_by_user_id = current_user.id
    charge.approved_at = datetime.utcnow()
    _log(charge, "approved", current_user)
    db.commit()
    return _serialize(_get_charge(db, charge_id))


@router.post("/{charge_id}/revise")
def revise_charge(
    charge_id: int,
    payload: ReviseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_access),
):
    """After approval, e.g. the insurer's answer changed. Deductions already
    made stay on record; someone left with more deducted than they now owe
    shows a refund due."""
    _ensure_can_approve(db, current_user)
    charge = _get_charge(db, charge_id)
    if charge.status != "approved":
        raise HTTPException(status_code=400, detail="Only an approved charge can be revised.")
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Give a reason for the revision.")
    if payload.charge_type != charge.charge_type or payload.trip_id != charge.trip_id:
        raise HTTPException(
            status_code=400, detail="The type and trip of an approved charge can't change."
        )
    _validate(db, payload)
    before = _money(charge.chargeable_amount)
    _apply_fields(charge, payload)
    _sync_allocations(charge, payload.allocations)
    db.flush()
    _ensure_shares_add_up(charge)
    now = datetime.utcnow()
    for allocation in charge.allocations:
        if allocation.notified_at is None:
            allocation.notified_at = now
    _log(
        charge,
        "revised",
        current_user,
        f"₱{before:,.2f} to ₱{_money(charge.chargeable_amount):,.2f}: {payload.reason.strip()}",
    )
    db.commit()
    return _serialize(_get_charge(db, charge_id))


@router.post("/{charge_id}/cancel")
def cancel_charge(
    charge_id: int,
    payload: ReasonIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_access),
):
    charge = _get_charge(db, charge_id)
    if charge.status == "approved":
        _ensure_can_approve(db, current_user)
    if charge.status == "cancelled":
        raise HTTPException(status_code=400, detail="This charge is already cancelled.")
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Give a reason for cancelling.")
    if any(_deducted(a) > 0 for a in charge.allocations):
        raise HTTPException(
            status_code=400,
            detail="Deductions were already made. Revise the charge instead.",
        )
    charge.status = "cancelled"
    _log(charge, "cancelled", current_user, payload.reason.strip())
    db.commit()
    return _serialize(_get_charge(db, charge_id))
