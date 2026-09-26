# app/api/admin/trip_manual_entries.py
#
# "Trip Manual Entries" -- superadmin records a whole trip that really
# happened but never made it through the driver's phone (e.g. the server
# was down that day). Unlike Trip Bypass, which walks an existing trip
# through each step, this creates the finished trip in one go: every
# assigned store delivered, no GPS/geofence checks, straight into the
# normal approval flow (Trip Approvals -> Office -> Finance -> payroll).
#
# Superadmin and coordinator_admin can enter trips. A coordinator_admin's
# entry waits in PENDING_MANUAL_APPROVAL until a superadmin approves it
# (then PENDING_APPROVAL) or rejects it (CANCELLED); a superadmin's own
# entry goes straight to PENDING_APPROVAL.

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import require_role_or_module, require_superadmin
from app.models.employees import Employee
from app.models.files import File as FileModel
from app.models.stores import Store
from app.models.trip_bypass_log import TripBypassLog
from app.models.trip_helper import TripHelper
from app.models.trip_stops import StopStatus, TripStop
from app.models.TripRate import TripRateProfile
from app.models.trips import Trip, TripStatus
from app.models.user import User, UserRole
from app.models.vehicle_unit import VehicleUnit
from app.services.file_service import FileService
from app.utils.timezone import ph_to_utc, utc_to_ph
from app.utils.user_display import display_name
from app.api.admin.trips import CANCELLED_TICKET_MARKER
from app.api.driver.trips import (
    MAX_PLANNED_STOPS,
    MAX_SHIPMENT_NUMBERS,
    _generate_trip_code,
    _invalid_shipment_number,
    _load_planned_store_ids,
)

router = APIRouter(prefix="/admin/trip-manual-entries", tags=["Trip Manual Entries"])

MANUAL_ENTRY_ACTION = "manual-entry"

# Who may open the page and enter trips. Only superadmin approves.
_require_entry_access = require_role_or_module(
    roles=["coordinator_admin"], module_key="trip_management.trip_manual_entries"
)


def _is_superadmin(user: User) -> bool:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return role.lower() == "superadmin"


def _parse_ph_time(value: str | None, label: str, required: bool = True):
    if value is None or not str(value).strip():
        if required:
            raise HTTPException(status_code=400, detail=f"{label} is required.")
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {label.lower()}.")
    when = ph_to_utc(parsed)
    if when > datetime.utcnow() + timedelta(minutes=5):
        raise HTTPException(
            status_code=400, detail=f"{label} can't be in the future."
        )
    return when


def _json_list(value, label: str) -> list:
    if value in (None, ""):
        return []
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Invalid {label} format.")
    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail=f"Invalid {label} format.")
    return data


def _fmt(dt):
    return utc_to_ph(dt).strftime("%Y-%m-%d %I:%M %p") if dt else None


@router.get("/options")
def get_manual_entry_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_entry_access),
):
    """Every driver, vehicle and helper -- including ones busy on a trip
    right now, since the trip being entered already happened."""
    drivers = (
        db.query(User)
        .options(joinedload(User.employee))
        .filter(User.role == UserRole.DRIVER)
        .order_by(User.username.asc())
        .all()
    )
    vehicles = (
        db.query(VehicleUnit)
        .filter(VehicleUnit.is_active.is_(True))
        .order_by(VehicleUnit.unit_code.asc())
        .all()
    )
    helpers = (
        db.query(Employee)
        .filter(Employee.position.ilike("helper"))
        .order_by(Employee.first_name.asc())
        .all()
    )
    return {
        "drivers": [
            {
                "id": d.id,
                "label": (
                    f"{d.employee.first_name} {d.employee.last_name} ({d.username})"
                    if d.employee
                    else d.username
                ),
                "is_active": bool(d.is_active),
            }
            for d in drivers
        ],
        "vehicles": [
            {
                "id": v.id,
                "label": " - ".join(
                    dict.fromkeys(filter(None, [v.unit_code, v.plate_number]))
                ),
            }
            for v in vehicles
        ],
        "helpers": [
            {"id": h.id, "label": f"{h.first_name} {h.last_name}"} for h in helpers
        ],
    }


@router.get("")
def list_manual_entries(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_entry_access),
):
    """Trips recorded on this page, newest first."""
    logs = (
        db.query(TripBypassLog)
        .filter(TripBypassLog.action == MANUAL_ENTRY_ACTION)
        .order_by(TripBypassLog.created_at.desc())
        .limit(200)
        .all()
    )
    if not logs:
        return []

    trips = {
        t.id: t
        for t in db.query(Trip)
        .options(joinedload(Trip.driver).joinedload(User.employee))
        .filter(Trip.id.in_([log.trip_id for log in logs]))
        .all()
    }
    # Approve/reject decisions per trip (latest wins).
    decisions = {}
    for d in (
        db.query(TripBypassLog)
        .filter(
            TripBypassLog.trip_id.in_([log.trip_id for log in logs]),
            TripBypassLog.action.in_(
                [f"{MANUAL_ENTRY_ACTION}-approved", f"{MANUAL_ENTRY_ACTION}-rejected"]
            ),
        )
        .order_by(TripBypassLog.created_at.asc())
    ):
        decisions[d.trip_id] = d

    user_ids = {log.performed_by_user_id for log in logs} | {
        d.performed_by_user_id for d in decisions.values()
    }
    creators = {
        u.id: u
        for u in db.query(User)
        .options(joinedload(User.employee))
        .filter(User.id.in_(user_ids))
        .all()
    }
    store_ids = {
        sid for t in trips.values() for sid in _load_planned_store_ids(t)
    }
    store_names = (
        {
            s.id: s.name
            for s in db.query(Store).filter(Store.id.in_(store_ids)).all()
        }
        if store_ids
        else {}
    )

    result = []
    for log in logs:
        trip = trips.get(log.trip_id)
        if not trip:
            continue
        creator = creators.get(log.performed_by_user_id)
        result.append(
            {
                "trip_id": trip.id,
                "trip_code": trip.trip_code,
                "ticket_no": trip.ticket_no,
                "driver_name": display_name(trip.driver) if trip.driver else None,
                "stores": [
                    store_names.get(sid, f"Store #{sid}")
                    for sid in _load_planned_store_ids(trip)
                ],
                "start_time": _fmt(trip.start_time),
                "end_time": _fmt(trip.end_time),
                "status": trip.status.value
                if hasattr(trip.status, "value")
                else trip.status,
                "reason": log.reason,
                "entered_by": display_name(creator) if creator else None,
                "entered_at": _fmt(log.created_at),
                "awaiting_approval": (
                    trip.status == TripStatus.PENDING_MANUAL_APPROVAL
                ),
                "decision": (
                    {
                        "approved": decision.action.endswith("-approved"),
                        "by": (
                            display_name(creators[decision.performed_by_user_id])
                            if decision.performed_by_user_id in creators
                            else None
                        ),
                        "at": _fmt(decision.created_at),
                        "reason": decision.reason,
                    }
                    if (decision := decisions.get(trip.id))
                    else None
                ),
            }
        )
    return result


@router.post("")
async def create_manual_entry(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_entry_access),
):
    """Multipart form:
    driver_id, vehicle_unit_id, origin_store_id, reason (required)
    shipment_numbers: JSON list of 8-digit numbers
    stops: JSON list in visiting order, each {store_id, arrived_at?,
      delivered_at?} (PH local "YYYY-MM-DDTHH:MM"; missing times are
      spread evenly between start and end)
    helper_ids: JSON list (optional)
    start_time, end_time: PH local date/time of Checkout and Checkin
    odometer_reading (optional)
    Photos (all optional): invoice_photo, lm_photo,
    lm_checkout_stamped_photo, stamped_invoice_photo (check-in LM), and
    pod_photo_<store_id> per store."""
    form = await request.form()

    reason = (form.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required.")

    # ---- driver
    try:
        driver_id = int(form.get("driver_id"))
        vehicle_unit_id = int(form.get("vehicle_unit_id"))
        origin_store_id = int(form.get("origin_store_id"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail="Driver, vehicle and origin hub are required."
        )

    driver = (
        db.query(User)
        .filter(User.id == driver_id, User.role == UserRole.DRIVER)
        .first()
    )
    if not driver:
        raise HTTPException(status_code=400, detail="Selected driver not found.")

    vehicle = db.query(VehicleUnit).filter(VehicleUnit.id == vehicle_unit_id).first()
    if not vehicle:
        raise HTTPException(status_code=400, detail="Selected vehicle not found.")

    origin = db.query(Store).filter(Store.id == origin_store_id).first()
    if not origin or not origin.is_hub:
        raise HTTPException(status_code=400, detail="Selected origin is not a valid hub.")

    # ---- times
    start_time = _parse_ph_time(form.get("start_time"), "Start (Checkout) time")
    end_time = _parse_ph_time(form.get("end_time"), "End (Checkin) time")
    if end_time <= start_time:
        raise HTTPException(
            status_code=400, detail="End (Checkin) time must be after the start time."
        )

    # No overlap with the same driver's other trips -- two trips at once
    # for one driver is almost always a typing mistake.
    other_trips = (
        db.query(Trip)
        .filter(
            Trip.driver_id == driver.id,
            Trip.start_time.isnot(None),
            Trip.status.notin_([TripStatus.ASSIGNED, TripStatus.CANCELLED]),
        )
        .all()
    )
    for other in other_trips:
        other_end = other.end_time or datetime.utcnow()
        if other.start_time < end_time and start_time < other_end:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"This overlaps the driver's trip {other.trip_code or other.id} "
                    f"({_fmt(other.start_time)} to "
                    f"{_fmt(other.end_time) or 'still in progress'})."
                ),
            )

    # ---- shipment numbers
    shipment_numbers = [
        str(n).strip()
        for n in _json_list(form.get("shipment_numbers"), "shipment number")
        if str(n).strip()
    ]
    if not shipment_numbers:
        raise HTTPException(status_code=400, detail="At least one shipment number is required.")
    if len(shipment_numbers) != len(set(shipment_numbers)):
        raise HTTPException(status_code=400, detail="Duplicate shipment numbers entered.")
    if len(shipment_numbers) > MAX_SHIPMENT_NUMBERS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_SHIPMENT_NUMBERS} shipment numbers allowed.",
        )
    bad = _invalid_shipment_number(shipment_numbers)
    if bad:
        raise HTTPException(
            status_code=400, detail=f'Shipment number "{bad}" must be exactly 8 digits.'
        )
    used = set()
    for other in db.query(Trip.ticket_no, Trip.shipment_numbers).all():
        if CANCELLED_TICKET_MARKER in (other.ticket_no or ""):
            continue
        if other.shipment_numbers:
            try:
                used.update(json.loads(other.shipment_numbers))
            except (TypeError, ValueError):
                pass
        elif other.ticket_no:
            used.add(other.ticket_no)
    duplicate = next((n for n in shipment_numbers if n in used), None)
    if duplicate:
        raise HTTPException(
            status_code=400, detail=f'Shipment number "{duplicate}" already exists.'
        )

    # ---- stops
    raw_stops = _json_list(form.get("stops"), "stores")
    if not raw_stops:
        raise HTTPException(status_code=400, detail="Select at least one destination store.")
    if len(raw_stops) > MAX_PLANNED_STOPS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_PLANNED_STOPS} destination stores allowed.",
        )
    try:
        store_ids = [int(s["store_id"]) for s in raw_stops]
    except (TypeError, KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid stores format.")
    if len(store_ids) != len(set(store_ids)):
        raise HTTPException(status_code=400, detail="Duplicate stores selected.")
    stores_by_id = {
        s.id: s for s in db.query(Store).filter(Store.id.in_(store_ids)).all()
    }
    for sid in store_ids:
        if sid not in stores_by_id:
            raise HTTPException(status_code=400, detail=f"Store {sid} not found.")

    primary = stores_by_id[store_ids[0]]
    rate_profile = (
        db.query(TripRateProfile)
        .filter(
            TripRateProfile.id == primary.trip_rate_profile_id,
            TripRateProfile.is_active.is_(True),
        )
        .first()
        if primary.trip_rate_profile_id
        else None
    )
    if not rate_profile:
        raise HTTPException(
            status_code=400,
            detail=f'"{primary.name}" has no active trip rate profile. Set one on the store first.',
        )

    # Per-stop times: entered ones are used; missing ones are spread
    # evenly across the trip so the timeline stays in order.
    count = len(raw_stops)
    span = end_time - start_time
    stop_times = []
    previous = start_time
    for index, raw in enumerate(raw_stops):
        name = stores_by_id[store_ids[index]].name
        default_arrived = start_time + span * (2 * index + 1) / (2 * count + 1)
        default_delivered = start_time + span * (2 * index + 2) / (2 * count + 1)
        arrived = (
            _parse_ph_time(raw.get("arrived_at"), f"Arrival time at {name}", required=False)
            or default_arrived
        )
        delivered = (
            _parse_ph_time(raw.get("delivered_at"), f"Delivered time at {name}", required=False)
            or max(default_delivered, arrived)
        )
        if not (previous <= arrived <= delivered <= end_time):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Times at {name} are out of order -- each store's arrival "
                    "and delivery must fall between the previous store and "
                    "the Checkin time."
                ),
            )
        stop_times.append((arrived, delivered))
        previous = delivered

    # ---- helpers (no availability lock -- this trip is already over)
    helper_ids = []
    for hid in _json_list(form.get("helper_ids"), "helper"):
        try:
            helper_ids.append(int(hid))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid helper format.")
    if len(helper_ids) != len(set(helper_ids)):
        raise HTTPException(status_code=400, detail="Duplicate helpers selected.")
    if len(helper_ids) > 3:
        raise HTTPException(status_code=400, detail="Maximum of 3 helpers allowed.")
    for hid in helper_ids:
        helper = db.query(Employee).filter(Employee.id == hid).first()
        if not helper or (helper.position or "").upper() != "HELPER":
            raise HTTPException(status_code=400, detail=f"Helper {hid} not found.")

    try:
        odometer = int(form.get("odometer_reading") or 0)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid odometer reading.")

    # ---- create
    trip = Trip(
        driver_id=driver.id,
        origin_store_id=origin.id,
        vehicle_unit_id=vehicle.id,
        destination_store_id=primary.id,
        planned_store_ids=json.dumps(store_ids),
        trip_rate_profile_id=rate_profile.id,
        ticket_no=", ".join(shipment_numbers),
        shipment_numbers=json.dumps(shipment_numbers),
        # A coordinator_admin's entry waits for a superadmin first.
        status=(
            TripStatus.PENDING_APPROVAL
            if _is_superadmin(current_user)
            else TripStatus.PENDING_MANUAL_APPROVAL
        ),
        current_step="CHECKIN",
        start_time=start_time,
        end_time=end_time,
        created_at=start_time,
        odometer_reading=odometer,
        dispatched_by_user_id=current_user.id,
    )
    db.add(trip)
    db.flush()
    trip.trip_code = _generate_trip_code(db, start_time)

    for hid in helper_ids:
        db.add(TripHelper(trip_id=trip.id, helper_id=hid))

    stops = []
    for sid, (arrived, delivered) in zip(store_ids, stop_times):
        stop = TripStop(
            trip_id=trip.id,
            store_id=sid,
            status=StopStatus.DELIVERED,
            check_in_time=arrived,
            check_out_time=delivered,
            requires_review=False,
        )
        db.add(stop)
        stops.append(stop)
    db.flush()

    # ---- photos (optional)
    file_service = FileService()

    def attach(field, uploader, entity_type, entity_id, document_type, *args):
        upload = form.get(field)
        if upload is None or not getattr(upload, "filename", None):
            return
        url = uploader(upload, *args)
        db.add(
            FileModel(
                entity_type=entity_type,
                entity_id=entity_id,
                document_type=document_type,
                file_url=url,
                uploaded_by=current_user.id,
            )
        )

    attach("invoice_photo", file_service.upload_trip_checkout_invoice,
           "trip", trip.id, "INVOICE_PHOTO", trip.id)
    attach("lm_photo", file_service.upload_trip_checkout_lm,
           "trip", trip.id, "LM_MANIFEST_PHOTO", trip.id)
    attach("lm_checkout_stamped_photo", file_service.upload_trip_checkout_lm_stamped,
           "trip", trip.id, "LM_CHECKOUT_STAMPED_PHOTO", trip.id)
    attach("stamped_invoice_photo", file_service.upload_trip_end_photo,
           "trip", trip.id, "STAMPED_INVOICE_PHOTO", trip.id)
    for stop in stops:
        attach(f"pod_photo_{stop.store_id}", file_service.upload_trip_pod_photo,
               "trip_stop", stop.id, "DELIVERY_PROOF_PHOTO", trip.id, stop.id)

    db.add(
        TripBypassLog(
            trip_id=trip.id,
            action=MANUAL_ENTRY_ACTION,
            performed_by_user_id=current_user.id,
            reason=reason,
        )
    )
    db.commit()

    return {
        "message": (
            "Trip entered. It's now waiting in Trip Approvals."
            if trip.status == TripStatus.PENDING_APPROVAL
            else "Trip entered. It's waiting for superadmin approval."
        ),
        "trip_id": trip.id,
        "trip_code": trip.trip_code,
        "awaiting_approval": trip.status == TripStatus.PENDING_MANUAL_APPROVAL,
    }


def _get_waiting_entry(db: Session, trip_id: int) -> Trip:
    trip = db.query(Trip).filter(Trip.id == trip_id).with_for_update().first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    if trip.status != TripStatus.PENDING_MANUAL_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail="This manual entry isn't waiting for approval anymore.",
        )
    return trip


@router.post("/{trip_id}/approve")
def approve_manual_entry(
    trip_id: int,
    remarks: str | None = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Superadmin accepts a coordinator_admin's entry -- it moves on to
    Trip Approvals like any finished trip."""
    trip = _get_waiting_entry(db, trip_id)
    trip.status = TripStatus.PENDING_APPROVAL
    db.add(
        TripBypassLog(
            trip_id=trip.id,
            action=f"{MANUAL_ENTRY_ACTION}-approved",
            performed_by_user_id=current_user.id,
            reason=(remarks or "").strip() or None,
        )
    )
    db.commit()
    return {"message": "Approved. The trip is now in Trip Approvals."}


@router.post("/{trip_id}/reject")
def reject_manual_entry(
    trip_id: int,
    reason: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Superadmin turns down a coordinator_admin's entry. The trip is
    cancelled and its shipment numbers are freed for a corrected entry."""
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required.")
    trip = _get_waiting_entry(db, trip_id)
    trip.status = TripStatus.CANCELLED
    trip.current_step = "CANCELLED"
    if trip.ticket_no:
        marker = f" {CANCELLED_TICKET_MARKER}{trip.id})"
        trip.ticket_no = trip.ticket_no[: 500 - len(marker)] + marker
    db.add(
        TripBypassLog(
            trip_id=trip.id,
            action=f"{MANUAL_ENTRY_ACTION}-rejected",
            performed_by_user_id=current_user.id,
            reason=reason,
        )
    )
    db.commit()
    return {"message": "Rejected. The entry was cancelled."}


# =========================
# BELL: entries waiting for superadmin approval
# =========================
@router.get("/waiting")
def list_waiting_entries(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Coordinator_admin entries still waiting for a superadmin -- what
    the Manual Entries alert bell shows (oldest first)."""
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.driver).joinedload(User.employee))
        .filter(Trip.status == TripStatus.PENDING_MANUAL_APPROVAL)
        .all()
    )
    if not trips:
        return []
    logs = {
        log.trip_id: log
        for log in db.query(TripBypassLog).filter(
            TripBypassLog.trip_id.in_([t.id for t in trips]),
            TripBypassLog.action == MANUAL_ENTRY_ACTION,
        )
    }
    users = {
        u.id: u
        for u in db.query(User)
        .options(joinedload(User.employee))
        .filter(User.id.in_({log.performed_by_user_id for log in logs.values()}))
        .all()
    }
    result = []
    for trip in trips:
        log = logs.get(trip.id)
        creator = users.get(log.performed_by_user_id) if log else None
        result.append(
            {
                "trip_id": trip.id,
                "trip_code": trip.trip_code,
                "ticket_no": trip.ticket_no,
                "driver_name": display_name(trip.driver) if trip.driver else None,
                "trip_date": _fmt(trip.start_time),
                "entered_by": display_name(creator) if creator else None,
                "entered_at": _fmt(log.created_at) if log else None,
                "_sort": log.created_at if log else trip.created_at,
            }
        )
    result.sort(key=lambda r: r["_sort"])
    for r in result:
        r.pop("_sort")
    return result


# =========================
# VIEW ONE ENTRY
# =========================
@router.get("/{trip_id}")
def get_manual_entry(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_entry_access),
):
    """Everything entered for one manual entry, for the View window."""
    entry_log = (
        db.query(TripBypassLog)
        .filter(
            TripBypassLog.trip_id == trip_id,
            TripBypassLog.action == MANUAL_ENTRY_ACTION,
        )
        .first()
    )
    if not entry_log:
        raise HTTPException(status_code=404, detail="Manual entry not found.")

    trip = (
        db.query(Trip)
        .options(
            joinedload(Trip.driver).joinedload(User.employee),
            joinedload(Trip.vehicle_unit),
            joinedload(Trip.origin_store),
            joinedload(Trip.trip_rate_profile),
            joinedload(Trip.trip_helpers).joinedload(TripHelper.helper),
        )
        .filter(Trip.id == trip_id)
        .first()
    )
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")

    decision = (
        db.query(TripBypassLog)
        .filter(
            TripBypassLog.trip_id == trip.id,
            TripBypassLog.action.in_(
                [f"{MANUAL_ENTRY_ACTION}-approved", f"{MANUAL_ENTRY_ACTION}-rejected"]
            ),
        )
        .order_by(TripBypassLog.created_at.desc())
        .first()
    )
    user_ids = {entry_log.performed_by_user_id}
    if decision:
        user_ids.add(decision.performed_by_user_id)
    users = {
        u.id: u
        for u in db.query(User)
        .options(joinedload(User.employee))
        .filter(User.id.in_(user_ids))
        .all()
    }

    stops = (
        db.query(TripStop)
        .filter(TripStop.trip_id == trip.id)
        .order_by(TripStop.check_in_time.asc(), TripStop.id.asc())
        .all()
    )
    store_names = {
        s.id: s.name
        for s in db.query(Store)
        .filter(Store.id.in_([st.store_id for st in stops if st.store_id] or [0]))
        .all()
    }

    trip_files = (
        db.query(FileModel)
        .filter(FileModel.entity_type == "trip", FileModel.entity_id == trip.id)
        .order_by(FileModel.id.asc())
        .all()
    )
    stop_files = (
        db.query(FileModel)
        .filter(
            FileModel.entity_type == "trip_stop",
            FileModel.entity_id.in_([st.id for st in stops] or [0]),
            FileModel.document_type == "DELIVERY_PROOF_PHOTO",
        )
        .all()
    )
    pod_by_stop = {f.entity_id: f.file_url for f in stop_files}
    photo_labels = {
        "INVOICE_PHOTO": "Invoice",
        "LM_MANIFEST_PHOTO": "LM",
        "LM_CHECKOUT_STAMPED_PHOTO": "LM (stamped 'checkout')",
        "STAMPED_INVOICE_PHOTO": "LM (stamped 'check-in')",
    }

    def name_of(user_id):
        user = users.get(user_id)
        return display_name(user) if user else None

    vehicle = trip.vehicle_unit
    return {
        "trip_id": trip.id,
        "trip_code": trip.trip_code,
        "status": trip.status.value if hasattr(trip.status, "value") else trip.status,
        "awaiting_approval": trip.status == TripStatus.PENDING_MANUAL_APPROVAL,
        "driver_name": display_name(trip.driver) if trip.driver else None,
        "vehicle": (
            " - ".join(dict.fromkeys(filter(None, [vehicle.unit_code, vehicle.plate_number])))
            if vehicle
            else None
        ),
        "origin": trip.origin_store.name if trip.origin_store else None,
        "trip_category": (
            trip.trip_rate_profile.profile_name if trip.trip_rate_profile else None
        ),
        "shipment_numbers": json.loads(trip.shipment_numbers)
        if trip.shipment_numbers
        else ([trip.ticket_no] if trip.ticket_no else []),
        "odometer_reading": trip.odometer_reading,
        "helpers": [
            f"{th.helper.first_name} {th.helper.last_name}"
            for th in trip.trip_helpers
            if th.helper
        ],
        "start_time": _fmt(trip.start_time),
        "end_time": _fmt(trip.end_time),
        "stops": [
            {
                "store_name": store_names.get(st.store_id, "Unknown store"),
                "arrived_at": _fmt(st.check_in_time),
                "delivered_at": _fmt(st.check_out_time),
                "pod_url": pod_by_stop.get(st.id),
            }
            for st in stops
        ],
        "photos": [
            {"label": photo_labels.get(f.document_type, f.document_type), "url": f.file_url}
            for f in trip_files
            if f.document_type in photo_labels
        ],
        "reason": entry_log.reason,
        "entered_by": name_of(entry_log.performed_by_user_id),
        "entered_at": _fmt(entry_log.created_at),
        "decision": (
            {
                "approved": decision.action.endswith("-approved"),
                "by": name_of(decision.performed_by_user_id),
                "at": _fmt(decision.created_at),
                "reason": decision.reason,
            }
            if decision
            else None
        ),
    }
