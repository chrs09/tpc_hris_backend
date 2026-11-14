# app/api/fuel_requests.py
#
# Driver fuel requests. Driver (mobile Fuel tab) sends an odometer photo,
# plate number and city -> coordinator admin (web Fuel Requests page)
# issues a fuel code + liters -> driver fuels up and uploads the receipt
# -> coordinator admin confirms it (Completed) or sends it back.
# When the Org Chart has heads with "Fuel Request" ticked above the
# driver, they approve it first (in order), before the fuel code.
# See app/models/fuel_request.py for the statuses.

from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role_or_module
from app.models.employees import Employee
from app.models.fuel_request import FuelRequest
from app.services.approval_chain import (
    acting_index,
    append_log,
    describe_chain,
    dump_chain,
    load_json_list,
    log_skipped,
    resolve_chain,
    skipped_for,
    team_scope,
)
from app.models.user import User, UserRole
from app.services.file_service import FileService
from app.models.trips import Trip, TripStatus
from app.models.vehicle_unit import VehicleUnit
from app.services.fleet_status import unit_statuses
from app.services.vehicle_assignment import assigned_unit_of, unit_label
from app.utils.timezone import ph_to_utc, utc_to_ph
from app.utils.user_display import display_name

router = APIRouter(prefix="/fuel-requests", tags=["Fuel Requests"])

# Requests still in progress -- a driver may only have one at a time.
OPEN_STATUSES = ("pending", "issued", "returned", "receipt_submitted")

# What the coordinator admin still has to act on: see _needs_action_filter
# (pending -- once past the Org Chart heads -- and receipt_submitted).

_require_coordinator = require_role_or_module(
    roles=["coordinator_admin"], module_key="fleet_management.fuel_requests"
)


def _fmt(dt):
    return utc_to_ph(dt).strftime("%b %d, %Y %I:%M %p") if dt else None


def _code_expired(req: FuelRequest) -> bool:
    """An issued code past its expiry. It is NOT closed automatically: the
    driver may have used it, so it stays open until they upload the
    receipt or mark it as not used (cancel-code, with a reason) -- and
    they can't request a new code until then. (Older rows may still have
    the former auto status "expired".)"""
    return bool(
        req.status in ("issued", "returned")
        and req.code_expires_at is not None
        and req.code_expires_at <= datetime.utcnow()
    )


def _needs_action_filter():
    # A pending request still with the Org Chart heads isn't the
    # coordinator's yet.
    return or_(
        (FuelRequest.status == "pending") & (FuelRequest.awaiting_approval.is_(False)),
        FuelRequest.status == "receipt_submitted",
    )


def _serialize(req: FuelRequest, db: Session | None = None) -> dict:
    chain_info = (
        describe_chain(
            db,
            req.approval_chain,
            req.approval_step,
            req.approval_log,
            not req.awaiting_approval,
        )
        if db is not None and req.approval_chain
        else {"approval_steps": [], "approval_log": load_json_list(req.approval_log)}
    )
    return {
        "id": req.id,
        "status": req.status,
        "driver_name": display_name(req.driver) if req.driver else None,
        "plate_number": req.plate_number,
        "city": req.city,
        "odo_photo_url": req.odo_photo_url,
        "odometer_reading": req.odometer_reading,
        "vehicle_unit_id": req.vehicle_unit_id,
        # Why it isn't the driver's assigned unit (None when it is).
        "unit_reason": req.unit_reason,
        "fuel_code": req.fuel_code,
        "liters": float(req.liters) if req.liters is not None else None,
        "issued_by": display_name(req.issued_by) if req.issued_by else None,
        "issued_at": _fmt(req.issued_at),
        "code_expires_at": _fmt(req.code_expires_at),
        # Past expiry, still waiting for the receipt (or "not used").
        "code_expired": _code_expired(req),
        "code_cancelled_at": _fmt(req.code_cancelled_at),
        "cancel_reason": req.cancel_reason,
        "receipt_photo_url": req.receipt_photo_url,
        "receipt_submitted_at": _fmt(req.receipt_submitted_at),
        "actual_liters": float(req.actual_liters) if req.actual_liters is not None else None,
        "actual_price": float(req.actual_price) if req.actual_price is not None else None,
        "completed_by": display_name(req.completed_by) if req.completed_by else None,
        "completed_at": _fmt(req.completed_at),
        "note": req.note,
        "created_at": _fmt(req.created_at),
        # Org chart approval progress (empty when there's no chain).
        "awaiting_approval": bool(req.awaiting_approval),
        "can_act": getattr(req, "_can_act", True),
        "viewer_away": getattr(req, "_away", None),
        **chain_info,
    }


def _query(db: Session):
    return db.query(FuelRequest).options(
        joinedload(FuelRequest.driver).joinedload(User.employee),
        joinedload(FuelRequest.issued_by).joinedload(User.employee),
        joinedload(FuelRequest.completed_by).joinedload(User.employee),
    )


def _require_image(upload: UploadFile, label: str):
    if upload is None or not upload.filename:
        raise HTTPException(status_code=400, detail=f"{label} is required.")
    if not (upload.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail=f"{label} must be an image.")


def _get_locked(db: Session, request_id: int) -> FuelRequest:
    req = (
        db.query(FuelRequest)
        .filter(FuelRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="Fuel request not found.")
    return req


def _is_driver(user: User) -> bool:
    return user.role == UserRole.DRIVER or str(user.role).lower().endswith("driver")


def _decimal_in_range(value, label: str, maximum: int, places: str = "0.01") -> Decimal:
    try:
        parsed = Decimal(str(value)).quantize(Decimal(places))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail=f"Invalid {label.lower()}.")
    if parsed <= 0 or parsed > maximum:
        raise HTTPException(
            status_code=400,
            detail=f"{label} must be more than 0 and at most {maximum:,}.",
        )
    return parsed


# =====================================================================
# DRIVER
# =====================================================================
def _unit_brief(unit: VehicleUnit, status: dict | None = None) -> dict:
    return {
        "id": unit.id,
        "plate_number": unit.plate_number,
        "unit_code": unit.unit_code,
        "description": unit.description,
        "status": status["status"] if status else None,
        "status_label": status["status_label"] if status else None,
        "status_reason": status["status_reason"] if status else None,
        "assigned_driver_name": (
            display_name(unit.assigned_driver) if unit.assigned_driver else None
        ),
    }


def _current_trip(db: Session, driver_user_id: int):
    """The driver's trip in progress (else the next dispatched one)."""
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.vehicle_unit))
        .filter(
            Trip.driver_id == driver_user_id,
            Trip.status.in_([TripStatus.ACTIVE, TripStatus.ASSIGNED]),
            Trip.vehicle_unit_id.isnot(None),
        )
        .order_by(Trip.id.desc())
        .all()
    )
    active = [t for t in trips if t.status == TripStatus.ACTIVE]
    return (active or trips or [None])[0]


def _unit_options(db: Session, user: User) -> dict:
    """Which unit a fuel request is for:

    - "trip":     the driver is on a trip in a unit other than their
                  assigned one -> that unit (locked).
    - "assigned": their assigned unit is fine -> it (locked).
    - "pick":     their unit is down (breakdown / maintenance / hold /
                  retired / in repair) or they have none -> they pick one
                  of the available units (`choices`).
    `reason` is saved on the request when it isn't the assigned unit.
    """
    assigned = assigned_unit_of(db, user.id)
    trip = _current_trip(db, user.id)
    assigned_status = unit_statuses(db, [assigned])[assigned.id] if assigned else None
    assigned_down = bool(
        assigned_status
        and assigned_status["status"] in ("breakdown", "maintenance", "hold", "retired")
    )

    out = {
        "mode": "pick",
        "unit": None,
        "reason": None,
        "assigned_unit": _unit_brief(assigned, assigned_status) if assigned else None,
        "trip_code": None,
        "choices": [],
    }

    if trip is not None and (assigned is None or trip.vehicle_unit_id != assigned.id):
        unit = trip.vehicle_unit
        trip_ref = trip.trip_code or trip.ticket_no or f"#{trip.id}"
        out.update(
            mode="trip",
            unit=_unit_brief(unit, unit_statuses(db, [unit])[unit.id]),
            trip_code=trip_ref,
            reason=(
                f"On trip {trip_ref} in {unit_label(unit)}"
                + (f" (assigned unit: {unit_label(assigned)})" if assigned else " (no assigned unit)")
            ),
        )
        return out

    if assigned is not None and not assigned_down:
        out.update(mode="assigned", unit=out["assigned_unit"])
        return out

    # Pick from the units free right now (not down, not on a trip).
    units = (
        db.query(VehicleUnit)
        .options(joinedload(VehicleUnit.assigned_driver).joinedload(User.employee))
        .filter(VehicleUnit.is_active.is_(True))
        .order_by(VehicleUnit.plate_number.asc())
        .all()
    )
    statuses = unit_statuses(db, units)
    choices = [
        _unit_brief(u, statuses[u.id])
        for u in units
        if statuses[u.id]["status"] == "available" and (assigned is None or u.id != assigned.id)
    ]
    # Units nobody owns first -- less likely to be needed by their driver.
    choices.sort(key=lambda c: (c["assigned_driver_name"] is not None, c["plate_number"] or ""))
    out["choices"] = choices
    if assigned is not None:
        why = assigned_status["status_reason"]
        out["reason"] = (
            f"Assigned unit {unit_label(assigned)} is on {assigned_status['status_label']}"
            + (f" ({why})" if why else "")
        )
    else:
        out["reason"] = "No assigned unit"
    return out


@router.get("/unit-options")
def fuel_unit_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """For the mobile Fuel form: the unit to fuel, or the units to pick
    from when the driver's own unit is down. See _unit_options."""
    return _unit_options(db, current_user)


@router.post("")
def create_fuel_request(
    city: str = Form(...),
    odo_photo: UploadFile = File(...),
    # Only used when the driver has to pick ("pick" in /unit-options);
    # otherwise the assigned / trip unit is used.
    vehicle_unit_id: int | None = Form(None),
    # Older app versions send a typed plate instead of a unit.
    plate_number: str | None = Form(None),
    # Odometer reading in km (typed; the photo is the proof).
    odometer_reading: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_driver(current_user):
        raise HTTPException(status_code=403, detail="Only drivers can request fuel.")

    options = _unit_options(db, current_user)
    unit_id = None
    unit_reason = options["reason"]
    if options["mode"] in ("assigned", "trip"):
        unit_id = options["unit"]["id"]
        plate_number = options["unit"]["plate_number"]
    elif vehicle_unit_id is not None:
        chosen = next((c for c in options["choices"] if c["id"] == vehicle_unit_id), None)
        if chosen is None:
            raise HTTPException(
                status_code=400,
                detail="That unit isn't available. Pull down to refresh and pick another.",
            )
        unit_id = chosen["id"]
        plate_number = chosen["plate_number"]
    else:
        # Older app: typed plate. Link it to a unit when it matches one.
        typed = (plate_number or "").strip().upper()
        match = (
            db.query(VehicleUnit).filter(VehicleUnit.plate_number == typed).first()
            if typed
            else None
        )
        unit_id = match.id if match else None
        if not typed:
            raise HTTPException(status_code=400, detail="Pick the unit you're fueling.")

    plate_number = (plate_number or "").strip().upper()
    city = city.strip()
    if not plate_number:
        raise HTTPException(status_code=400, detail="Plate number is required.")
    if not city:
        raise HTTPException(status_code=400, detail="City is required.")
    _require_image(odo_photo, "Odometer photo")
    if odometer_reading is not None and not 0 <= odometer_reading <= 9_999_999:
        raise HTTPException(status_code=400, detail="Enter a valid odometer reading.")

    open_request = (
        db.query(FuelRequest)
        .filter(
            FuelRequest.user_id == current_user.id,
            FuelRequest.status.in_(OPEN_STATUSES),
        )
        .first()
    )
    if open_request and _code_expired(open_request):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Fuel code {open_request.fuel_code or ''} expired on "
                f"{_fmt(open_request.code_expires_at)}. Upload its receipt first, "
                "or mark it as not used, before requesting a new code."
            ),
        )
    if open_request:
        raise HTTPException(
            status_code=400,
            detail="You still have a fuel request in progress. Finish it first.",
        )

    # Org chart approver (below). None -> straight to the coordinator.
    employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
        if current_user.employee_id
        else None
    )
    # Only the NEAREST head above the driver with Fuel Request ticked: they
    # approve and issue the code (e.g. Wingvan's head for Wingvan drivers;
    # the Coordinator for units without their own fuel approver).
    chain = resolve_chain(db, employee, current_user, "fuel_request")[:1]

    req = FuelRequest(
        user_id=current_user.id,
        employee_id=current_user.employee_id,
        plate_number=plate_number,
        vehicle_unit_id=unit_id,
        unit_reason=unit_reason,
        city=city,
        odo_photo_url="",
        odometer_reading=odometer_reading,
        status="pending",
        approval_chain=dump_chain(chain),
        approval_step=0,
        awaiting_approval=bool(chain),
    )
    db.add(req)
    db.flush()
    req.odo_photo_url = FileService().upload(odo_photo, f"fuel_requests/{req.id}/odo")
    db.commit()

    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


@router.get("/mine")
def list_my_fuel_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        _query(db)
        .filter(FuelRequest.user_id == current_user.id)
        .order_by(FuelRequest.created_at.desc())
        .limit(50)
        .all()
    )
    return [_serialize(r, db) for r in rows]


@router.post("/{request_id}/receipt")
def submit_fuel_receipt(
    request_id: int,
    receipt_photo: UploadFile = File(...),
    # From the receipt: liters actually pumped and the total amount paid.
    # Required by the app; optional here so older app versions still work.
    actual_liters: float | None = Form(None),
    actual_price: float | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_locked(db, request_id)
    if req.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Fuel request not found.")
    # Past its expiry is fine: the code may have been used, and the receipt
    # is what closes it ("expired" = older rows closed automatically).
    if req.status not in ("issued", "returned", "expired"):
        raise HTTPException(
            status_code=400,
            detail="A receipt can only be sent after the fuel code is issued.",
        )
    _require_image(receipt_photo, "Receipt photo")
    liters_value = (
        _decimal_in_range(actual_liters, "Actual liters", 1000)
        if actual_liters is not None
        else None
    )
    price_value = (
        _decimal_in_range(actual_price, "Actual price", 1_000_000)
        if actual_price is not None
        else None
    )

    req.actual_liters = liters_value
    req.actual_price = price_value
    req.receipt_photo_url = FileService().upload(
        receipt_photo, f"fuel_requests/{req.id}/receipt"
    )
    req.receipt_submitted_at = datetime.utcnow()
    req.status = "receipt_submitted"
    db.commit()

    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


@router.post("/{request_id}/cancel")
def cancel_fuel_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_locked(db, request_id)
    if req.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Fuel request not found.")
    if req.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Only a request still waiting for a fuel code can be cancelled.",
        )
    req.status = "cancelled"
    db.commit()
    return {"message": "Fuel request cancelled."}


@router.post("/{request_id}/cancel-code")
def cancel_fuel_code(
    request_id: int,
    reason: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Driver drops an issued code they won't use / didn't use (e.g.
    changed unit) -- also how a code past its expiry that was never used is
    closed ("Not used"). The reason is shown to the coordinator; then they
    can request a new one."""
    req = _get_locked(db, request_id)
    if req.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Fuel request not found.")
    if req.status != "issued":
        raise HTTPException(
            status_code=400,
            detail="Only an issued code that hasn't been used can be cancelled.",
        )
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Please enter a reason.")
    req.status = "code_cancelled"
    req.cancel_reason = reason[:1000]
    req.code_cancelled_at = datetime.utcnow()
    db.commit()
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


# =====================================================================
# COORDINATOR ADMIN (web)
# =====================================================================
@router.get("")
def list_fuel_requests(
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    """`status`: a single status, "open" (everything still in progress),
    or omitted for all. Newest first."""
    q = _query(db)
    if status == "open":
        q = q.filter(FuelRequest.status.in_(OPEN_STATUSES))
    elif status == "needs_action":
        q = q.filter(_needs_action_filter())
    elif status == "unused":
        # Codes never used: expired or cancelled by the driver.
        q = q.filter(FuelRequest.status.in_(("expired", "code_cancelled")))
    elif status == "awaiting_approval":
        q = q.filter(FuelRequest.status == "pending", FuelRequest.awaiting_approval.is_(True))
    elif status:
        q = q.filter(FuelRequest.status == status)
    rows = q.order_by(FuelRequest.created_at.desc()).limit(300).all()
    return [_serialize(r, db) for r in rows]


@router.get("/alerts")
def fuel_request_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    """For the web bell: requests waiting for a fuel code or a receipt
    check, oldest first."""
    rows = (
        _query(db)
        .filter(_needs_action_filter())
        .order_by(FuelRequest.updated_at.asc())
        .all()
    )
    return [_serialize(r, db) for r in rows]


# =====================================================================
# ORG CHART HEADS -- approve / reject before the fuel code
# =====================================================================
def _is_chain_approver(req: FuelRequest, user: User) -> bool:
    """The Org Chart head on this request's approval chain (they approve
    it and then issue the fuel code -- see create_fuel_request)."""
    return user.id in [int(i) for i in load_json_list(req.approval_chain)]


def _ensure_can_handle(request: Request, db: Session, req: FuelRequest, user: User):
    """Coordinator access (Fuel Requests), or the head on its chain."""
    if _is_chain_approver(req, user):
        return
    _require_coordinator(request=request, current_user=user, db=db)


def _is_superadmin(user: User) -> bool:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return role == "superadmin"


@router.get("/for-my-approval")
def list_fuel_for_my_approval(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fuel requests whose turn is with me on the Org Chart chain (or
    passed up past me because I'm away today -- read-only). Superadmin
    sees every request still awaiting approval."""
    rows = (
        _query(db)
        .filter(FuelRequest.status == "pending", FuelRequest.awaiting_approval.is_(True))
        .order_by(FuelRequest.created_at.asc())
        .all()
    )
    if _is_superadmin(current_user):
        return [_serialize(r, db) for r in rows]

    team = team_scope(db, current_user)
    mine = []
    for req in rows:
        if team is not None and req.employee_id not in team["employee_ids"]:
            continue
        chain = [int(i) for i in load_json_list(req.approval_chain)]
        if acting_index(db, chain, req.approval_step, current_user.id)[0] is not None:
            req._can_act = True
            mine.append(req)
        else:
            away = skipped_for(db, chain, req.approval_step, current_user.id)
            if away:
                req._can_act = False
                req._away = away
                mine.append(req)
    return [_serialize(r, db) for r in mine]


def _approval_turn(db: Session, req: FuelRequest, current_user: User):
    """(chain, acting step or None, skipped). The head whose turn it is
    acts on their step; a superadmin may act at any point."""
    if req.status != "pending" or not req.awaiting_approval:
        raise HTTPException(status_code=400, detail="This request isn't waiting for approval.")
    chain = [int(i) for i in load_json_list(req.approval_chain)]
    acting, skipped = acting_index(db, chain, req.approval_step, current_user.id)
    if acting is None and not _is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="It isn't your turn to approve this request.")
    return chain, acting, skipped


@router.post("/{request_id}/approve")
def approve_fuel_request(
    request_id: int,
    remarks: str | None = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_locked(db, request_id)
    chain, acting, skipped = _approval_turn(db, req, current_user)
    req.approval_log = log_skipped(db, req.approval_log, chain, skipped)
    req.approval_log = append_log(req.approval_log, current_user, "approved", remarks)

    if acting is not None and acting < len(chain) - 1:
        # Pass it to the next head up.
        req.approval_step = acting + 1
    else:
        # Last head (or a superadmin): over to the coordinator for the code.
        req.approval_step = len(chain)
        req.awaiting_approval = False
    db.commit()
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


@router.post("/{request_id}/reject")
def reject_fuel_request(
    request_id: int,
    reason: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_locked(db, request_id)
    chain, _acting, skipped = _approval_turn(db, req, current_user)
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required.")
    req.approval_log = log_skipped(db, req.approval_log, chain, skipped)
    req.approval_log = append_log(req.approval_log, current_user, "rejected", reason)
    req.status = "declined"
    req.note = reason
    req.awaiting_approval = False
    db.commit()
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


@router.get("/{request_id}")
def get_fuel_request(
    request_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _query(db).filter(FuelRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Fuel request not found.")
    _ensure_can_handle(request, db, req, current_user)
    return _serialize(req, db)


@router.post("/{request_id}/issue")
def issue_fuel_code(
    request_id: int,
    fuel_code: str = Body(..., embed=True),
    liters: float = Body(..., embed=True),
    # "YYYY-MM-DDTHH:MM", Philippine time. Past it the code stays open
    # until the driver uploads the receipt or marks it not used.
    code_expires_at: str | None = Body(None, embed=True),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_locked(db, request_id)
    # Coordinator, or the Org Chart head who approved it.
    _ensure_can_handle(request, db, req, current_user)
    if req.status != "pending":
        raise HTTPException(
            status_code=400, detail="This request already has a fuel code."
        )
    if req.awaiting_approval:
        raise HTTPException(
            status_code=400,
            detail="This request is still waiting for Org Chart approval.",
        )
    fuel_code = (fuel_code or "").strip()
    if not fuel_code:
        raise HTTPException(status_code=400, detail="Fuel code is required.")
    try:
        liters_value = Decimal(str(liters)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="Invalid liters.")
    if liters_value <= 0 or liters_value > 1000:
        raise HTTPException(
            status_code=400, detail="Liters must be more than 0 and at most 1,000."
        )

    expires_utc = None
    if code_expires_at:
        try:
            expires_utc = ph_to_utc(datetime.fromisoformat(code_expires_at.strip()))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expiry date.")
        if expires_utc <= datetime.utcnow():
            raise HTTPException(status_code=400, detail="The expiry must be in the future.")

    req.fuel_code = fuel_code
    req.code_expires_at = expires_utc
    req.liters = liters_value
    req.issued_by_user_id = current_user.id
    req.issued_at = datetime.utcnow()
    req.status = "issued"
    db.commit()
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


@router.post("/{request_id}/decline")
def decline_fuel_request(
    request_id: int,
    reason: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    req = _get_locked(db, request_id)
    if req.status != "pending":
        raise HTTPException(
            status_code=400, detail="Only a request waiting for a fuel code can be declined."
        )
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required.")
    req.status = "declined"
    req.note = reason
    req.completed_by_user_id = current_user.id
    req.completed_at = datetime.utcnow()
    db.commit()
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


@router.post("/{request_id}/complete")
def complete_fuel_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    req = _get_locked(db, request_id)
    if req.status != "receipt_submitted":
        raise HTTPException(
            status_code=400, detail="There's no receipt waiting to be confirmed."
        )
    req.status = "completed"
    req.note = None
    req.completed_by_user_id = current_user.id
    req.completed_at = datetime.utcnow()
    db.commit()
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


@router.post("/{request_id}/return")
def return_fuel_receipt(
    request_id: int,
    reason: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    """Receipt is wrong/unreadable -- the driver uploads a new one."""
    req = _get_locked(db, request_id)
    if req.status != "receipt_submitted":
        raise HTTPException(
            status_code=400, detail="There's no receipt waiting to be confirmed."
        )
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required.")
    req.status = "returned"
    req.note = reason
    db.commit()
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)
