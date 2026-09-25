# app/api/admin/trips.py

from app.models.gps_log import GPSLog
from app.models.trip_models import GPSActionType
from app.schemas import trip
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Body,
    UploadFile,
    File as FastAPIFile,
)
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, date, timedelta

from app.core.database import get_db
from app.core.dependencies import get_current_trip_manager, get_current_user, require_role_or_module
from app.models.trips import Trip, TripStatus
from app.models.notification import Notification
from app.models.trip_stops import TripStop, StopStatus
from app.models.user import User, UserRole
from app.models.employees import Employee
from app.models.trip_helper import TripHelper
from app.models.trip_bypass_log import TripBypassLog
from app.models.trip_finance_review import FinanceReviewStatus, TripFinanceReview
from app.models.files import File
from app.models.stores import Store
from app.services.file_service import FileService
from app.utils.timezone import utc_to_ph
from app.utils.user_display import display_name as _display_name
from app.api.driver.trips import (
    _load_planned_store_ids,
    _delivered_store_ids,
    _load_shipment_numbers,
    _invalid_shipment_number,
    _helper_departments_for,
    MAX_PLANNED_STOPS,
    MAX_SHIPMENT_NUMBERS,
)
from app.models.vehicle_unit import VehicleUnit
from app.models.TripRate import TripRateProfile
from pydantic import BaseModel
import json

router = APIRouter(prefix="/admin/trips", tags=["Admin Trips"])


# Human-readable label for each Trip.current_step value -- shown on the
# Trip Dashboard's Active Trips list so a coordinator can see exactly
# which driver-triggered step a trip is on right now (e.g. the driver
# tapping "Checkout" on their phone moves current_step straight to
# IN_TRANSIT, since Checkout now starts the trip in one action -- see
# checkout_trip() in app/api/driver/trips.py). RETURNING is a legacy
# fallback for trips stuck there from before "Back to Source" was
# removed.
CURRENT_STEP_LABELS = {
    "ASSIGNED": "Assigned (Not Started)",
    "IN_TRANSIT": "Checked Out (In Transit)",
    "ARRIVED": "Arrived at Store",
    "UNLOADING": "Unloading",
    "DELIVERED": "Delivered",
    "RETURNING": "Returning to Hub",
    "CHECKIN": "Checked In (At Hub)",
}


def _current_step_label(current_step: str | None) -> str:
    return CURRENT_STEP_LABELS.get(current_step, current_step or "-")


def _current_stop_name(db: Session, trip: Trip) -> str | None:
    """Best-effort "where is this trip right now" label: the open stop's
    store while ARRIVED/UNLOADING, the last delivered store while
    DELIVERED, or the next undelivered planned store otherwise (e.g.
    IN_TRANSIT, heading there)."""
    if trip.current_step in ("ARRIVED", "UNLOADING"):
        open_stop = (
            db.query(TripStop)
            .filter(
                TripStop.trip_id == trip.id,
                TripStop.status != StopStatus.DELIVERED,
            )
            .order_by(TripStop.id.desc())
            .first()
        )
        if open_stop and open_stop.store:
            return open_stop.store.name

    planned_ids = _load_planned_store_ids(trip)
    if not planned_ids:
        return None

    delivered_ids = _delivered_store_ids(db, trip.id)

    if trip.current_step == "DELIVERED":
        last_delivered = (
            db.query(TripStop)
            .filter(
                TripStop.trip_id == trip.id,
                TripStop.status == StopStatus.DELIVERED,
            )
            .order_by(TripStop.id.desc())
            .first()
        )
        if last_delivered and last_delivered.store:
            return last_delivered.store.name

    remaining_ids = [sid for sid in planned_ids if sid not in delivered_ids]
    if remaining_ids:
        next_store = db.query(Store).filter(Store.id == remaining_ids[0]).first()
        if next_store:
            return next_store.name

    return None


# =========================
# SUMMARY
# =========================
@router.get("/summary")
def get_trip_summary(
    db: Session = Depends(get_db), current_admin=Depends(require_role_or_module(roles=["admin", "superadmin", "coordinator_admin", "coordinator"], module_key="trip_management.trips"))
):
    today = date.today()

    return {
        "assigned_trips": db.query(Trip)
        .filter(Trip.status == TripStatus.ASSIGNED)
        .count(),
        "pending_trips": db.query(Trip)
        .filter(Trip.status == TripStatus.PENDING_APPROVAL)
        .count(),
        "active_trips": db.query(Trip).filter(Trip.status == TripStatus.ACTIVE).count(),
        "completed_today": db.query(Trip)
        .filter(Trip.status == TripStatus.COMPLETED, Trip.end_time >= today)
        .count(),
    }


# =========================
# GET AVAILABLE DRIVERS
#
# Drivers a trip manager can start a trip for (see the driver_id bypass
# on POST /driver/trips/start) -- active accounts with no trip already
# in progress.
# =========================
@router.get("/available-drivers")
def get_available_drivers(
    db: Session = Depends(get_db), current_admin=Depends(require_role_or_module(roles=["admin", "superadmin", "coordinator_admin", "coordinator"], module_key="trip_management.trips"))
):
    drivers_with_active_trip = {
        row[0]
        for row in db.query(Trip.driver_id)
        .filter(Trip.status == TripStatus.ACTIVE)
        .all()
    }

    drivers = (
        db.query(User)
        .options(joinedload(User.employee))
        .filter(User.role == UserRole.DRIVER, User.is_active.is_(True))
        .order_by(User.username.asc())
        .all()
    )

    return [
        {
            "id": driver.id,
            "username": driver.username,
            "employee_id": driver.employee_id,
            "employee_name": (
                f"{driver.employee.first_name} {driver.employee.last_name}"
                if driver.employee
                else None
            ),
        }
        for driver in drivers
        if driver.id not in drivers_with_active_trip
    ]


# =========================
# GET PENDING
# =========================
@router.get("/pending")
def get_pending_trips(
    db: Session = Depends(get_db), current_admin=Depends(require_role_or_module(roles=["admin", "superadmin", "coordinator_admin"], module_key="trip_management.trips"))
):
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.driver))
        .filter(
            Trip.status == TripStatus.PENDING_APPROVAL,
            Trip.is_archived.is_(False),
        )
        .order_by(Trip.start_time.desc())
        .all()
    )

    # Batched lookup (not per-row) of return reasons, so trips office
    # sent back for correction show a badge in the list without
    # requiring the coordinator to open each one first.
    trip_ids = [trip.id for trip in trips]
    return_reasons = {}
    if trip_ids:
        returned_reviews = (
            db.query(TripFinanceReview)
            .filter(
                TripFinanceReview.trip_id.in_(trip_ids),
                TripFinanceReview.status == FinanceReviewStatus.RETURNED,
            )
            .all()
        )
        return_reasons = {r.trip_id: r.return_reason for r in returned_reviews}

    # Assigned stores per trip, in the coordinator's route order. One
    # store lookup for the whole list rather than one per trip.
    planned_by_trip = {trip.id: _load_planned_store_ids(trip) for trip in trips}
    all_store_ids = {sid for ids in planned_by_trip.values() for sid in ids}
    store_names = (
        {
            store.id: store.name
            for store in db.query(Store).filter(Store.id.in_(all_store_ids)).all()
        }
        if all_store_ids
        else {}
    )

    return [
        {
            "id": trip.id,
            "trip_code": trip.trip_code,
            "ticket_no": trip.ticket_no,
            "trip_code": trip.trip_code,
            "status": trip.status.value,
            "start_time": utc_to_ph(trip.start_time).strftime("%Y-%m-%d %I:%M:%S %p"),
            "stops_count": db.query(TripStop)
            .filter(TripStop.trip_id == trip.id)
            .count(),
            "username": trip.driver.username,
            "return_reason": return_reasons.get(trip.id),
            "stores": [
                store_names.get(sid, f"Store #{sid}")
                for sid in planned_by_trip[trip.id]
            ],
        }
        for trip in trips
    ]


# =========================
# GET ACTIVE
# =========================
@router.get("/active")
def get_active_trips(
    db: Session = Depends(get_db), current_admin=Depends(require_role_or_module(roles=["admin", "superadmin", "coordinator_admin", "coordinator"], module_key="trip_management.trip_dashboard"))
):
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.driver))
        .filter(Trip.status == TripStatus.ACTIVE)
        .order_by(Trip.start_time.desc())
        .all()
    )

    result = []
    for trip in trips:
        planned_ids = _load_planned_store_ids(trip)
        delivered_ids = _delivered_store_ids(db, trip.id) if planned_ids else set()

        result.append(
            {
                "id": trip.id,
                "trip_code": trip.trip_code,
                "ticket_no": trip.ticket_no,
                "vehicle_unit": (trip.vehicle_unit.unit_code if trip.vehicle_unit else "-"),
                "trip_profile": (
                    trip.trip_rate_profile.profile_name if trip.trip_rate_profile else "-"
                ),
                "status": trip.status.value,
                "current_step": trip.current_step,
                "current_step_label": _current_step_label(trip.current_step),
                "current_stop": _current_stop_name(db, trip),
                "total_stops": len(planned_ids) if planned_ids else None,
                "completed_stops": len(delivered_ids) if planned_ids else None,
                "start_time": utc_to_ph(trip.start_time).strftime("%Y-%m-%d %I:%M:%S %p"),
                "username": trip.driver.username,
                "started_outside_hub_range": trip.started_outside_hub_range,
            }
        )

    return result


# =========================
# GET ASSIGNED (dispatched, driver hasn't checked out yet)
# =========================
@router.get("/assigned")
def get_assigned_trips(
    db: Session = Depends(get_db), current_admin=Depends(require_role_or_module(roles=["admin", "superadmin", "coordinator_admin", "coordinator"], module_key="trip_management.trip_dashboard"))
):
    trips = (
        db.query(Trip)
        .options(
            joinedload(Trip.driver).joinedload(User.employee),
            joinedload(Trip.dispatched_by).joinedload(User.employee),
            joinedload(Trip.trip_helpers).joinedload(TripHelper.helper),
        )
        .filter(Trip.status == TripStatus.ASSIGNED)
        .order_by(Trip.created_at.desc())
        .all()
    )

    result = []
    for trip in trips:
        planned_ids = _load_planned_store_ids(trip)
        stores_by_id = (
            {
                store.id: store
                for store in db.query(Store)
                .filter(Store.id.in_(planned_ids))
                .all()
            }
            if planned_ids
            else {}
        )
        # In the coordinator's chosen visiting order.
        destination_names = [
            stores_by_id[sid].name for sid in planned_ids if sid in stores_by_id
        ]

        result.append(
            {
                "id": trip.id,
                "trip_code": trip.trip_code,
                "ticket_no": trip.ticket_no,
                "driver_name": _display_name(trip.driver),
                "dispatched_by_name": (
                    _display_name(trip.dispatched_by)
                    if trip.dispatched_by
                    else "-"
                ),
                "vehicle_unit": (
                    trip.vehicle_unit.unit_code if trip.vehicle_unit else "-"
                ),
                "trip_profile": (
                    trip.trip_rate_profile.profile_name
                    if trip.trip_rate_profile
                    else "-"
                ),
                "origin_store": (
                    trip.origin_store.name if trip.origin_store else "-"
                ),
                "destinations": destination_names,
                "current_step": trip.current_step,
                "current_step_label": _current_step_label(trip.current_step),
                # Once the driver has begun Checkout, photos are attached,
                # so the dispatch details are frozen.
                "editable": trip.current_step == "ASSIGNED",
                "driver_id": trip.driver_id,
                "vehicle_unit_id": trip.vehicle_unit_id,
                "origin_store_id": trip.origin_store_id,
                "destination_store_ids": planned_ids,
                "shipment_numbers": _load_shipment_numbers(trip),
                "helpers": [
                    {
                        "id": th.helper.id,
                        "name": f"{th.helper.first_name} {th.helper.last_name}",
                    }
                    for th in trip.trip_helpers
                    if th.helper
                ],
                "dispatched_at": (
                    utc_to_ph(trip.created_at).strftime("%Y-%m-%d %I:%M:%S %p")
                    if trip.created_at
                    else None
                ),
            }
        )

    return result


# =========================
# CANCEL AN UNSTARTED TRIP
# =========================
# Marker appended to a cancelled trip's ticket_no. ticket_no is UNIQUE, so
# without this the shipment number(s) would stay locked to the cancelled
# trip and the same shipment could never be dispatched again -- which is
# the whole point of cancelling a dispatch made by mistake. The dispatch
# duplicate check skips trips carrying this marker (see dispatch_trip).
CANCELLED_TICKET_MARKER = "(cancelled #"


@router.post("/{trip_id}/cancel")
def cancel_unstarted_trip(
    trip_id: int,
    reason: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_admin=Depends(
        require_role_or_module(
            roles=["admin", "superadmin", "coordinator_admin", "coordinator"],
            module_key="trip_management.trip_dashboard",
        )
    ),
):
    """Undoes a dispatch: a trip the driver hasn't started (still
    ASSIGNED) is cancelled, and its vehicle and helpers are released.
    Whoever can dispatch a trip can cancel it. A trip already in progress
    can't be cancelled here -- it has real steps recorded on it, so it goes
    through Trip Bypass and the normal approve/reject review instead."""
    reason = reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required.")

    trip = (
        db.query(Trip)
        .options(
            joinedload(Trip.trip_helpers).joinedload(TripHelper.helper),
            joinedload(Trip.vehicle_unit),
        )
        .filter(Trip.id == trip_id)
        .first()
    )
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")

    if trip.status != TripStatus.ASSIGNED:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only a trip the driver hasn't started yet can be "
                "cancelled. For one already in progress, use Trip Bypass."
            ),
        )

    trip.status = TripStatus.CANCELLED
    trip.current_step = "CANCELLED"

    if trip.ticket_no:
        marker = f" {CANCELLED_TICKET_MARKER}{trip.id})"
        trip.ticket_no = trip.ticket_no[: 500 - len(marker)] + marker

    if trip.vehicle_unit:
        trip.vehicle_unit.is_available = True

    for trip_helper in trip.trip_helpers:
        if trip_helper.helper:
            trip_helper.helper.is_available = 1

    db.add(
        TripBypassLog(
            trip_id=trip.id,
            action="cancel",
            performed_by_user_id=current_admin.id,
            reason=reason,
        )
    )
    db.commit()

    return {"message": "Trip cancelled.", "trip_id": trip.id}


# =========================
# EDIT AN UNSTARTED TRIP'S DISPATCH DETAILS
# =========================
class AssignedTripUpdate(BaseModel):
    driver_id: int
    vehicle_unit_id: int
    origin_store_id: int
    destination_store_ids: list[int]
    shipment_numbers: list[str]
    helper_ids: list[int] = []
    reason: str | None = None


@router.put("/{trip_id}/assignment")
def update_assigned_trip(
    trip_id: int,
    payload: AssignedTripUpdate,
    db: Session = Depends(get_db),
    current_admin=Depends(
        require_role_or_module(
            roles=["admin", "superadmin", "coordinator_admin", "coordinator"],
            module_key="trip_management.trip_dashboard",
        )
    ),
):
    """Corrects a dispatch the driver hasn't started working on yet. Same
    rules as dispatching (see dispatch_trip), except the trip's own
    driver, vehicle, helpers and shipment numbers don't count as "already
    taken" against itself. Vehicle/helper availability is swapped over for
    whatever changed."""
    trip = (
        db.query(Trip)
        .options(
            joinedload(Trip.trip_helpers).joinedload(TripHelper.helper),
            joinedload(Trip.vehicle_unit),
        )
        .filter(Trip.id == trip_id)
        .with_for_update()
        .first()
    )
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    if trip.status != TripStatus.ASSIGNED or trip.current_step != "ASSIGNED":
        raise HTTPException(
            status_code=400,
            detail=(
                "This trip can no longer be edited -- the driver has "
                "already started it. Use Trip Bypass instead."
            ),
        )

    # ---- shipment numbers
    shipment_numbers = [n.strip() for n in payload.shipment_numbers if n.strip()]
    if not shipment_numbers:
        raise HTTPException(status_code=400, detail="At least one shipment number is required.")
    bad_number = _invalid_shipment_number(shipment_numbers)
    if bad_number:
        raise HTTPException(
            status_code=400,
            detail=f'Shipment number "{bad_number}" must be exactly 8 digits.',
        )
    if len(shipment_numbers) != len(set(shipment_numbers)):
        raise HTTPException(status_code=400, detail="Duplicate shipment numbers entered.")
    if len(shipment_numbers) > MAX_SHIPMENT_NUMBERS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_SHIPMENT_NUMBERS} shipment numbers allowed.",
        )

    used = set()
    for other in db.query(Trip.id, Trip.ticket_no, Trip.shipment_numbers).all():
        if other.id == trip.id or CANCELLED_TICKET_MARKER in (other.ticket_no or ""):
            continue
        if other.shipment_numbers:
            try:
                used.update(json.loads(other.shipment_numbers))
            except Exception:
                pass
        elif other.ticket_no:
            used.add(other.ticket_no)
    duplicate = next((n for n in shipment_numbers if n in used), None)
    if duplicate:
        raise HTTPException(
            status_code=400, detail=f'Shipment number "{duplicate}" already exists.'
        )

    # ---- destinations
    dest_ids = payload.destination_store_ids
    if not dest_ids:
        raise HTTPException(status_code=400, detail="Select at least one destination store.")
    if len(dest_ids) != len(set(dest_ids)):
        raise HTTPException(status_code=400, detail="Duplicate stores selected.")
    if len(dest_ids) > MAX_PLANNED_STOPS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_PLANNED_STOPS} destination stores allowed.",
        )
    stores_by_id = {
        st.id: st for st in db.query(Store).filter(Store.id.in_(dest_ids)).all()
    }
    for sid in dest_ids:
        if sid not in stores_by_id:
            raise HTTPException(status_code=400, detail=f"Store {sid} not found.")
    primary_store = stores_by_id[dest_ids[0]]
    if not primary_store.trip_rate_profile_id:
        raise HTTPException(
            status_code=400,
            detail=f'"{primary_store.name}" has no trip rate profile configured.',
        )
    rate_profile = (
        db.query(TripRateProfile)
        .filter(
            TripRateProfile.id == primary_store.trip_rate_profile_id,
            TripRateProfile.is_active.is_(True),
        )
        .first()
    )
    if not rate_profile:
        raise HTTPException(
            status_code=400,
            detail=f'"{primary_store.name}" trip rate profile is inactive.',
        )

    # ---- driver
    driver = (
        db.query(User)
        .options(joinedload(User.employee))
        .filter(User.id == payload.driver_id, User.role == UserRole.DRIVER)
        .first()
    )
    if not driver or not driver.employee:
        raise HTTPException(status_code=400, detail="Selected driver not found.")
    if driver.id != trip.driver_id:
        busy = (
            db.query(Trip.id)
            .filter(
                Trip.driver_id == driver.id,
                Trip.id != trip.id,
                Trip.status.in_([TripStatus.ASSIGNED, TripStatus.ACTIVE]),
            )
            .first()
        )
        if busy:
            raise HTTPException(
                status_code=400, detail="This driver already has a trip in progress."
            )

    # ---- vehicle (its own current one is held by this trip, so allowed)
    vehicle = (
        db.query(VehicleUnit)
        .filter(VehicleUnit.id == payload.vehicle_unit_id, VehicleUnit.is_active.is_(True))
        .first()
    )
    if not vehicle or (
        vehicle.id != trip.vehicle_unit_id and not vehicle.is_available
    ):
        raise HTTPException(status_code=400, detail="Selected vehicle is unavailable.")

    origin = db.query(Store).filter(Store.id == payload.origin_store_id).first()
    if not origin or not origin.is_hub:
        raise HTTPException(status_code=400, detail="Selected origin is not a valid hub.")

    # ---- helpers
    if len(payload.helper_ids) != len(set(payload.helper_ids)):
        raise HTTPException(status_code=400, detail="Duplicate helpers selected.")
    if len(payload.helper_ids) > 3:
        raise HTTPException(status_code=400, detail="Maximum of 3 helpers allowed.")
    current_helper_ids = {th.helper_id for th in trip.trip_helpers}
    allowed_departments = _helper_departments_for(driver.employee.department)
    new_helpers = {}
    for hid in payload.helper_ids:
        helper = db.query(Employee).filter(Employee.id == hid).first()
        if not helper:
            raise HTTPException(status_code=404, detail=f"Helper {hid} not found.")
        if (helper.position or "").upper() != "HELPER":
            raise HTTPException(status_code=400, detail="Invalid helper position.")
        if helper.department not in allowed_departments:
            raise HTTPException(status_code=400, detail="Helper department mismatch.")
        if hid not in current_helper_ids and not helper.is_available:
            raise HTTPException(
                status_code=400, detail=f"{helper.first_name} is unavailable."
            )
        new_helpers[hid] = helper

    # ---- what changed
    changes = []
    if driver.id != trip.driver_id:
        changes.append("driver")
    if vehicle.id != trip.vehicle_unit_id:
        changes.append("vehicle")
    if origin.id != trip.origin_store_id:
        changes.append("origin hub")
    if shipment_numbers != _load_shipment_numbers(trip):
        changes.append("shipment numbers")
    if dest_ids != _load_planned_store_ids(trip):
        changes.append("destinations")
    if set(payload.helper_ids) != current_helper_ids:
        changes.append("helpers")
    if not changes:
        raise HTTPException(status_code=400, detail="No changes to save.")

    # ---- apply
    if vehicle.id != trip.vehicle_unit_id:
        if trip.vehicle_unit:
            trip.vehicle_unit.is_available = True
        vehicle.is_available = False

    for th in list(trip.trip_helpers):
        if th.helper_id not in new_helpers:
            if th.helper:
                th.helper.is_available = 1
            db.delete(th)
    for hid, helper in new_helpers.items():
        if hid not in current_helper_ids:
            helper.is_available = 0
            db.add(TripHelper(trip_id=trip.id, helper_id=hid))

    trip.driver_id = driver.id
    trip.vehicle_unit_id = vehicle.id
    trip.origin_store_id = origin.id
    trip.destination_store_id = primary_store.id
    trip.planned_store_ids = json.dumps(dest_ids)
    trip.trip_rate_profile_id = rate_profile.id
    trip.shipment_numbers = json.dumps(shipment_numbers)
    trip.ticket_no = ", ".join(shipment_numbers)

    summary = "Edited " + ", ".join(changes) + "."
    if payload.reason and payload.reason.strip():
        summary += f" {payload.reason.strip()}"
    db.add(
        TripBypassLog(
            trip_id=trip.id,
            action="edit",
            performed_by_user_id=current_admin.id,
            reason=summary,
        )
    )
    db.commit()

    return {"message": "Trip updated.", "trip_id": trip.id, "changed": changes}


# =========================
# APPROVE TRIP
# =========================

@router.post("/{trip_id}/approve")
def approve_trip(
    trip_id: int,
    remarks: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_admin=Depends(require_role_or_module(roles=["admin", "superadmin", "coordinator_admin"], module_key="trip_management.trips")),
):
    # =========================================================
    # 1. GET TRIP
    # =========================================================

    trip = (
        db.query(Trip)
        .filter(Trip.id == trip_id)
        .first()
    )

    if not trip:
        raise HTTPException(
            status_code=404,
            detail="Trip not found",
        )

    # =========================================================
    # 2. VERIFY TRIP IS WAITING FOR COORDINATOR
    # =========================================================

    if trip.status != TripStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail="Trip is not pending coordinator approval",
        )

    # =========================================================
    # 3. VALIDATE COORDINATOR REMARKS
    # =========================================================

    if not remarks or not remarks.strip():
        raise HTTPException(
            status_code=400,
            detail="Coordinator remarks are required",
        )

    # =========================================================
    # 4. PREVENT DUPLICATE REVIEW RECORD -- UNLESS OFFICE SENT IT BACK
    #
    # trip_id is unique on tpc_trip_finance_reviews, so a trip that has
    # already been through the review cycle once still has a row here.
    # If office sent it back for correction (status RETURNED), this is
    # a legitimate re-approval -- reuse that same row instead of
    # blocking. Any other existing status means the trip shouldn't be
    # PENDING_APPROVAL at all (data inconsistency), so still block.
    # =========================================================

    existing_review = (
        db.query(TripFinanceReview)
        .filter(
            TripFinanceReview.trip_id == trip.id
        )
        .first()
    )

    if existing_review and existing_review.status != FinanceReviewStatus.RETURNED:
        raise HTTPException(
            status_code=400,
            detail="Trip already has a review record",
        )

    # =========================================================
    # 5. SET COORDINATOR SETTLEMENT DATE
    # =========================================================

    now = datetime.utcnow()

    # =========================================================
    # 6. MOVE TRIP TO OFFICE REVIEW
    # =========================================================

    trip.status = TripStatus.PENDING_OFFICE_REVIEW

    # =========================================================
    # 7. CREATE OR REUSE REVIEW RECORD
    # =========================================================

    if existing_review:
        review = existing_review
        review.coordinator_id = current_admin.id
        review.coordinator_remarks = remarks.strip()
        review.coordinator_settlement_date = now
        review.status = FinanceReviewStatus.OFFICE_REVIEW
    else:
        review = TripFinanceReview(
            trip_id=trip.id,
            coordinator_id=current_admin.id,
            coordinator_remarks=remarks.strip(),
            coordinator_settlement_date=now,
            status=FinanceReviewStatus.OFFICE_REVIEW,
        )
        db.add(review)

    # =========================================================
    # 8. UPDATE EXISTING TRIP COMPLETION NOTIFICATION
    # =========================================================

    notification = (
        db.query(Notification)
        .filter(
            Notification.trip_id == trip.id,
            Notification.type == "TRIP_COMPLETED",
            Notification.status == "PENDING",
        )
        .first()
    )

    if notification:
        notification.status = "APPROVED"
        notification.reviewed_by_admin_id = current_admin.id
        notification.reviewed_at = now

    # =========================================================
    # 9. SAVE CHANGES
    # =========================================================

    db.commit()

    db.refresh(trip)
    db.refresh(review)

    # =========================================================
    # 10. RESPONSE
    # =========================================================

    coordinator_name = _display_name(current_admin)

    return {
        "message": (
            f"Trip approved by {coordinator_name} "
            "and sent for office review"
        ),
        "trip_id": trip.id,
        "trip_status": trip.status.value,
        "review_status": review.status.value,
        "coordinator_id": review.coordinator_id,
        "coordinator_name": coordinator_name,
        "coordinator_settlement_date": (
            review.coordinator_settlement_date
        ),
    }

@router.post("/{trip_id}/reject")
def reject_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(require_role_or_module(roles=["admin", "superadmin", "coordinator_admin"], module_key="trip_management.trips")),
):

    trip = (
        db.query(Trip)
        .options(
            joinedload(Trip.trip_helpers),
            joinedload(Trip.vehicle_unit),
        )
        .filter(Trip.id == trip_id)
        .first()
    )

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")

    if trip.status != TripStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="Trip not pending approval.")

    trip.status = TripStatus.CANCELLED

    notification = (
        db.query(Notification)
        .filter(
            Notification.trip_id == trip.id,
            Notification.type == "TRIP_COMPLETED",
            Notification.status == "PENDING",
        )
        .first()
    )

    if notification:
        notification.status = "REJECTED"
        notification.reviewed_by_admin_id = current_admin.id
        notification.reviewed_at = datetime.utcnow()

    for trip_helper in trip.trip_helpers:
        if trip_helper.helper:
            trip_helper.helper.is_available = True

    if trip.vehicle_unit:
        trip.vehicle_unit.is_available = True

    db.commit()

    return {"message": "Trip rejected."}


# =========================
# REVIEW TRIP
# =========================
@router.get("/{trip_id}/review")
def review_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(require_role_or_module(roles=["admin", "superadmin", "coordinator_admin"], module_key="trip_management.trips")),
):
    # =========================================================
    # 1. GET TRIP + RELATED DATA
    # =========================================================
    trip = (
        db.query(Trip)
        .options(
            joinedload(Trip.driver).joinedload(User.employee),
            joinedload(Trip.origin_store),
            joinedload(Trip.vehicle_unit),
            joinedload(Trip.trip_rate_profile),
            joinedload(Trip.stops).joinedload(TripStop.store),
        )
        .filter(Trip.id == trip_id)
        .first()
    )

    if not trip:
        raise HTTPException(
            status_code=404,
            detail="Trip not found.",
        )

    # If office sent this trip back with a reason, surface it here so
    # the coordinator sees why before re-reviewing/re-approving.
    finance_review = (
        db.query(TripFinanceReview)
        .filter(TripFinanceReview.trip_id == trip_id)
        .first()
    )

    # =========================================================
    # 2. GET TRIP HELPERS
    # =========================================================
    trip_helpers = (
        db.query(Employee)
        .join(
            TripHelper,
            TripHelper.helper_id == Employee.id,
        )
        .filter(
            TripHelper.trip_id == trip_id,
        )
        .all()
    )

    helpers_data = [
        {
            "id": helper.id,
            "first_name": helper.first_name,
            "last_name": helper.last_name,
        }
        for helper in trip_helpers
    ]

    # =========================================================
    # 3. GET CHECKOUT PHOTOS (Invoice + LM -- each may have multiple
    # pages, plus the single LM stamped/marked "checkout")
    #
    # Expected:
    # entity_type   = trip
    # entity_id     = trip_id
    # document_type = INVOICE_PHOTO / LM_MANIFEST_PHOTO /
    #                  LM_CHECKOUT_STAMPED_PHOTO
    # =========================================================
    checkout_photos = (
        db.query(File)
        .filter(
            File.entity_type == "trip",
            File.entity_id == trip_id,
            File.document_type.in_(
                ["INVOICE_PHOTO", "LM_MANIFEST_PHOTO", "LM_CHECKOUT_STAMPED_PHOTO"]
            ),
        )
        .order_by(File.id.asc())
        .all()
    )

    invoice_photos = [
        {"id": f.id, "url": f.file_url}
        for f in checkout_photos
        if f.document_type == "INVOICE_PHOTO"
    ]
    lm_photos = [
        {"id": f.id, "url": f.file_url}
        for f in checkout_photos
        if f.document_type == "LM_MANIFEST_PHOTO"
    ]
    lm_checkout_stamped_photo = next(
        (
            {"id": f.id, "url": f.file_url}
            for f in reversed(checkout_photos)
            if f.document_type == "LM_CHECKOUT_STAMPED_PHOTO"
        ),
        None,
    )

    # =========================================================
    # 4. GET END TRIP / STAMPED INVOICE PHOTO
    #
    # Expected:
    # entity_type   = trip
    # entity_id     = trip_id
    # document_type = STAMPED_INVOICE_PHOTO
    #
    # Example path:
    # /uploads/trips/49/end/xxx.jpg
    # =========================================================
    stamped_invoice_photo = (
        db.query(File)
        .filter(
            File.entity_type == "trip",
            File.entity_id == trip_id,
            File.document_type == "STAMPED_INVOICE_PHOTO",
        )
        .order_by(File.id.desc())
        .first()
    )

    # =========================================================
    # 5. GET GPS LOGS
    # =========================================================
    gps_logs = (
        db.query(GPSLog)
        .filter(
            GPSLog.trip_id == trip_id,
        )
        .order_by(
            GPSLog.created_at.asc(),
        )
        .limit(5000)
        .all()
    )

    gps_logs_data = [
        {
            "id": log.id,
            "action_type": (
                log.action_type.value
                if hasattr(log.action_type, "value")
                else log.action_type
            ),
            "actual_lat": (
                float(log.actual_lat)
                if log.actual_lat is not None
                else None
            ),
            "actual_long": (
                float(log.actual_long)
                if log.actual_long is not None
                else None
            ),
            "accuracy": log.accuracy,
            "speed": log.speed,
            "created_at": (
                log.created_at.isoformat()
                if log.created_at
                else None
            ),
        }
        for log in gps_logs
    ]

    # =========================================================
    # 6. UTC -> PH TIME FORMATTER
    # =========================================================
    def to_ph(dt):
        if not dt:
            return None

        return utc_to_ph(dt).strftime(
            "%b %d, %Y, %I:%M %p"
        )

    # =========================================================
    # 7. SORT STOPS BY CHECK-IN TIME
    # =========================================================
    sorted_stops = sorted(
        trip.stops,
        key=lambda x: (
            x.check_in_time
            or datetime.min
        ),
    )

    # =========================================================
    # 8. GET ALL STOP IDS
    # =========================================================
    stop_ids = [
        stop.id
        for stop in sorted_stops
    ]

    # =========================================================
    # 9. GET ALL DELIVERY PROOF PHOTOS
    #
    # Expected:
    # entity_type   = trip_stop
    # entity_id     = stop.id
    # document_type = DELIVERY_PROOF_PHOTO
    #
    # Example:
    # Trip ID = 49
    # Stop ID = 45
    #
    # File path:
    # /uploads/trips/49/pod/45/xxx.jpg
    #
    # Database:
    # entity_type = trip_stop
    # entity_id   = 45
    # =========================================================
    delivery_proof_photos = []

    if stop_ids:
        delivery_proof_photos = (
            db.query(File)
            .filter(
                File.entity_type == "trip_stop",
                File.entity_id.in_(stop_ids),
                File.document_type
                == "DELIVERY_PROOF_PHOTO",
            )
            .order_by(
                File.id.desc(),
            )
            .all()
        )

    # =========================================================
    # 9.5 GET ALL UNLOADING PHOTOS
    #
    # Expected:
    # entity_type   = trip_stop
    # entity_id     = stop.id
    # document_type = UNLOADING_PHOTO
    # =========================================================
    unloading_photos = []

    if stop_ids:
        unloading_photos = (
            db.query(File)
            .filter(
                File.entity_type == "trip_stop",
                File.entity_id.in_(stop_ids),
                File.document_type == "UNLOADING_PHOTO",
            )
            .order_by(File.id.desc())
            .all()
        )

    # =========================================================
    # 10. CREATE POD + UNLOADING LOOKUPS
    #
    # Example:
    #
    # {
    #     45: "http://localhost:8000/uploads/trips/49/pod/45/a.jpg",
    #     46: "http://localhost:8000/uploads/trips/49/pod/46/b.jpg"
    # }
    #
    # Because photos are ordered newest first,
    # only keep the newest photo for each stop.
    # =========================================================
    delivery_proof_by_stop_id = {}

    for photo in delivery_proof_photos:
        if (
            photo.entity_id
            not in delivery_proof_by_stop_id
        ):
            delivery_proof_by_stop_id[photo.entity_id] = {
                "id": photo.id,
                "url": photo.file_url,
            }

    unloading_photo_by_stop_id = {}

    for photo in unloading_photos:
        if photo.entity_id not in unloading_photo_by_stop_id:
            unloading_photo_by_stop_id[photo.entity_id] = {
                "id": photo.id,
                "url": photo.file_url,
            }

    # =========================================================
    # 11. BUILD STOPS DATA
    # =========================================================
    stops_data = []

    for stop in sorted_stops:
        stops_data.append(
            {
                # TripStop ID
                "id": stop.id,

                # Store information
                "store_id": stop.store_id,
                "store_name": (
                    stop.store.name
                    if stop.store
                    else "Unknown"
                ),

                # CHECKED_IN / UNLOADING / DELIVERED
                "status": (
                    stop.status.value
                    if hasattr(stop.status, "value")
                    else stop.status
                ),

                # Check-in / Check-out
                "check_in_time": to_ph(
                    stop.check_in_time
                ),
                "check_out_time": to_ph(
                    stop.check_out_time
                ),

                # Actual recorded GPS
                "lat_in": stop.lat_in,
                "long_in": stop.long_in,
                "lat_out": stop.lat_out,
                "long_out": stop.long_out,

                # Official store coordinates
                "store_lat": (
                    stop.store.latitude
                    if stop.store
                    else None
                ),
                "store_long": (
                    stop.store.longitude
                    if stop.store
                    else None
                ),

                # Allowed GPS radius
                "allowed_radius": (
                    stop.store.allowed_radius_meters
                    if stop.store
                    else None
                ),

                # Unloading photo
                "unloading_photo": unloading_photo_by_stop_id.get(stop.id),

                # POD / Delivery Proof
                "delivery_proof_photo": (
                    delivery_proof_by_stop_id.get(
                        stop.id
                    )
                ),
            }
        )

    # =========================================================
    # 11.5 PLANNED STOPS (the coordinator's full route, set at dispatch --
    # like a parcel tracker, shows every stop on the itinerary, not just
    # the ones already visited).
    # =========================================================
    planned_ids = _load_planned_store_ids(trip)
    delivered_ids = _delivered_store_ids(db, trip.id) if planned_ids else set()
    planned_stores_data = []
    next_store = None
    if planned_ids:
        stores_by_id = {
            store.id: store
            for store in db.query(Store).filter(Store.id.in_(planned_ids)).all()
        }
        planned_stores_data = [
            {
                "store_id": sid,
                "store_name": stores_by_id[sid].name if sid in stores_by_id else None,
                "delivered": sid in delivered_ids,
            }
            for sid in planned_ids
        ]
        next_store = next(
            (s["store_name"] for s in planned_stores_data if not s["delivered"]),
            None,
        )

    # =========================================================
    # 11.6 TRIP BYPASS REMARKS -- steps a coordinator completed on the
    # driver's behalf, with the reason they entered for each.
    # =========================================================
    bypass_action_labels = {
        "checkout": "Checkout",
        "check-in": "Arrived at Store",
        "start-unloading": "Start Unloading",
        "check-out": "Delivered",
        "checkin": "Checkin",
        "assign-store": "Linked stop to store",
        "edit": "Edited dispatch",
        "reorder": "Changed stop order",
    }
    bypass_logs = (
        db.query(TripBypassLog)
        .filter(TripBypassLog.trip_id == trip.id)
        .order_by(TripBypassLog.created_at.asc(), TripBypassLog.id.asc())
        .all()
    )
    bypass_user_ids = {log.performed_by_user_id for log in bypass_logs}
    bypass_users = (
        {
            user.id: user
            for user in db.query(User)
            .options(joinedload(User.employee))
            .filter(User.id.in_(bypass_user_ids))
            .all()
        }
        if bypass_user_ids
        else {}
    )
    bypass_remarks = [
        {
            "id": log.id,
            "action": log.action,
            "action_label": bypass_action_labels.get(log.action, log.action),
            "reason": log.reason,
            "performed_by": (
                _display_name(bypass_users[log.performed_by_user_id])
                if log.performed_by_user_id in bypass_users
                else None
            ),
            "created_at": to_ph(log.created_at),
        }
        for log in bypass_logs
    ]

    # =========================================================
    # 12. RETURN COMPLETE TRIP REVIEW DATA
    # =========================================================
    return {
        "bypass_remarks": bypass_remarks,
        # -------------------------
        # TRIP
        # -------------------------
        "trip_id": trip.id,
        "trip_code": trip.trip_code,
        "ticket_no": trip.ticket_no,
        "trip_code": trip.trip_code,
        "current_step": trip.current_step,
        "current_step_label": _current_step_label(trip.current_step),
        "current_stop": _current_stop_name(db, trip),
        "status": (
            trip.status.value
            if hasattr(trip.status, "value")
            else trip.status
        ),

        # -------------------------
        # VEHICLE
        # -------------------------
        "vehicle": (
            {
                "id": trip.vehicle_unit.id,
                "unit_code": (
                    trip.vehicle_unit.unit_code
                ),
                "plate_number": (
                    trip.vehicle_unit.plate_number
                ),
            }
            if trip.vehicle_unit
            else None
        ),

        # -------------------------
        # TRIP RATE PROFILE
        # -------------------------
        "trip_rate_profile": (
            {
                "id": (
                    trip.trip_rate_profile.id
                ),
                "profile_name": (
                    trip.trip_rate_profile.profile_name
                ),
                "helper_count": (
                    trip.trip_rate_profile.helper_count
                ),
            }
            if trip.trip_rate_profile
            else None
        ),

        # -------------------------
        # DRIVER
        # -------------------------
        "driver_first_name": (
            trip.driver.employee.first_name
            if trip.driver
            and trip.driver.employee
            else "-"
        ),

        "driver_last_name": (
            trip.driver.employee.last_name
            if trip.driver
            and trip.driver.employee
            else "-"
        ),

        # -------------------------
        # HELPERS
        # -------------------------
        "helpers": helpers_data,

        # -------------------------
        # ORIGIN
        # -------------------------
        "origin_store": (
            trip.origin_store.name
            if trip.origin_store
            else "-"
        ),

        "origin_lat": (
            trip.origin_store.latitude
            if trip.origin_store
            else None
        ),

        "origin_long": (
            trip.origin_store.longitude
            if trip.origin_store
            else None
        ),

        # -------------------------
        # TIMES
        # -------------------------
        "start_time": to_ph(
            trip.start_time
        ),

        "end_time": to_ph(
            trip.end_time
        ),

        # -------------------------
        # TRIP PHOTOS
        # -------------------------
        # Checkout photos (may be multiple pages each for Invoice/LM)
        "invoice_photos": invoice_photos,
        "lm_photos": lm_photos,
        "lm_checkout_stamped_photo": lm_checkout_stamped_photo,

        "stamped_invoice_photo": (
            {"id": stamped_invoice_photo.id, "url": stamped_invoice_photo.file_url}
            if stamped_invoice_photo
            else None
        ),

        # -------------------------
        # STOPS + POD (actual TripStop rows visited so far)
        # -------------------------
        "stops": stops_data,

        # -------------------------
        # PLANNED ROUTE (parcel-tracker style -- every stop the
        # coordinator picked at dispatch, delivered or not)
        # -------------------------
        "planned_stores": planned_stores_data,
        "total_stops": len(planned_ids) if planned_ids else None,
        "completed_stops": len(delivered_ids) if planned_ids else None,
        "next_store": next_store,

        # -------------------------
        # GPS ROUTE
        # -------------------------
        "gps_logs": gps_logs_data,

        # -------------------------
        # RETURNED-FOR-CORRECTION (set only if office sent this trip
        # back -- see return_trip_to_approval in app/api/office/trips.py)
        # -------------------------
        "return_reason": (
            finance_review.return_reason
            if finance_review
            and finance_review.status == FinanceReviewStatus.RETURNED
            else None
        ),
        "returned_at": (
            to_ph(finance_review.returned_at)
            if finance_review
            and finance_review.status == FinanceReviewStatus.RETURNED
            else None
        ),
    }


# =========================
# OVERRIDE A TRIP DOCUMENT PHOTO
#
# Lets a coordinator replace a specific uploaded photo (invoice, LM,
# stamped LM, unloading, POD, stamped invoice) in place -- e.g. the
# driver photographed the wrong document, or the shot is unreadable.
# The File row itself is reused (same id, same document_type), only
# file_url changes -- so every existing screen that already reads that
# document_type keeps working with no further changes.
# =========================
@router.post("/files/{file_id}/replace")
def replace_trip_file(
    file_id: int,
    photo: UploadFile = FastAPIFile(...),
    db: Session = Depends(get_db),
    current_admin=Depends(require_role_or_module(roles=["admin", "superadmin", "coordinator_admin"], module_key="trip_management.trips")),
):
    file_row = db.query(File).filter(File.id == file_id).first()

    if not file_row:
        raise HTTPException(status_code=404, detail="File not found.")

    if file_row.entity_type == "trip":
        trip_id = file_row.entity_id
    elif file_row.entity_type == "trip_stop":
        stop = db.query(TripStop).filter(TripStop.id == file_row.entity_id).first()
        if not stop:
            raise HTTPException(status_code=404, detail="Trip stop not found.")
        trip_id = stop.trip_id
    else:
        raise HTTPException(
            status_code=400, detail="This file cannot be overridden here."
        )

    file_service = FileService()
    new_url = file_service.upload(
        photo, f"trips/{trip_id}/overrides/{file_row.document_type.lower()}"
    )

    file_row.file_url = new_url
    file_row.uploaded_by = current_admin.id

    db.commit()
    db.refresh(file_row)

    return {
        "message": "Photo replaced.",
        "file_id": file_row.id,
        "document_type": file_row.document_type,
        "file_url": file_row.file_url,
    }


@router.get("/completed")
def get_completed_trips(
    db: Session = Depends(get_db),
    current_admin=Depends(require_role_or_module(roles=["admin", "superadmin", "coordinator_admin"], module_key="trip_management.trips")),
):
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.driver))
        .filter(
            Trip.status == TripStatus.COMPLETED,
            Trip.is_archived.is_(False),
        )
        .order_by(Trip.end_time.desc())
        .all()
    )

    # A trip only becomes COMPLETED when Finance approves it (see
    # app/api/finance/trips.py) -- who approved it and when.
    trip_ids = [trip.id for trip in trips]
    finance_reviews = (
        {
            review.trip_id: review
            for review in db.query(TripFinanceReview)
            .options(
                joinedload(TripFinanceReview.finance_reviewer).joinedload(
                    User.employee
                )
            )
            .filter(TripFinanceReview.trip_id.in_(trip_ids))
            .all()
        }
        if trip_ids
        else {}
    )

    planned_by_trip = {trip.id: _load_planned_store_ids(trip) for trip in trips}
    all_store_ids = {sid for ids in planned_by_trip.values() for sid in ids}
    store_names = (
        {
            store.id: store.name
            for store in db.query(Store).filter(Store.id.in_(all_store_ids)).all()
        }
        if all_store_ids
        else {}
    )

    def finance_info(trip_id):
        review = finance_reviews.get(trip_id)
        if not review or review.status != FinanceReviewStatus.APPROVED:
            return {"status_label": "Completed"}
        return {
            "status_label": "Approved by Finance",
            "finance_approved_by": (
                _display_name(review.finance_reviewer)
                if review.finance_reviewer
                else None
            ),
            "finance_approved_at": (
                utc_to_ph(review.approved_at).strftime("%Y-%m-%d %I:%M %p")
                if review.approved_at
                else None
            ),
        }

    return [
        {
            "id": trip.id,
            "trip_code": trip.trip_code,
            "ticket_no": trip.ticket_no,
            "trip_code": trip.trip_code,
            "status": trip.status.value,
            "start_time": utc_to_ph(trip.start_time).strftime("%Y-%m-%d %I:%M:%S %p"),
            "end_time": (
                utc_to_ph(trip.end_time).strftime("%Y-%m-%d %I:%M:%S %p")
                if trip.end_time
                else None
            ),
            "stops_count": db.query(TripStop)
                .filter(TripStop.trip_id == trip.id)
                .count(),
            "username": trip.driver.username,
            "stores": [
                store_names.get(sid, f"Store #{sid}")
                for sid in planned_by_trip[trip.id]
            ],
            **finance_info(trip.id),
        }
        for trip in trips
    ]


# =========================
# ARCHIVE (soft delete)
#
# Hides a trip from get_pending_trips()/get_completed_trips() above
# without deleting the row (or its stops/GPS logs/files) -- an
# alternative to manually deleting from the database to clean up a long
# pending/completed-trips list. Reversible in the database if ever
# needed (is_archived can be flipped back), though there's no
# "unarchive" endpoint/button yet since nothing asked for one.
# =========================
ARCHIVABLE_STATUSES = [TripStatus.PENDING_APPROVAL, TripStatus.COMPLETED]


@router.post("/{trip_id}/archive")
def archive_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(require_role_or_module(roles=["admin", "superadmin", "coordinator_admin"], module_key="trip_management.trips")),
):
    trip_row = db.query(Trip).filter(Trip.id == trip_id).first()

    if not trip_row:
        raise HTTPException(status_code=404, detail="Trip not found.")

    if trip_row.status not in ARCHIVABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Only pending or completed trips can be archived.",
        )

    if trip_row.is_archived:
        raise HTTPException(status_code=400, detail="Trip is already archived.")

    trip_row.is_archived = True
    trip_row.archived_at = datetime.utcnow()
    trip_row.archived_by_user_id = current_admin.id

    db.commit()

    return {"message": "Trip archived.", "trip_id": trip_row.id}


@router.post("/{trip_id}/track-location")
def track_location(
    trip_id: int,
    payload: trip.LocationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):

    gps_log = GPSLog(
        trip_id=trip_id,
        action_type=GPSActionType.TRACK,
        actual_lat=payload.lat,
        actual_long=payload.long,
    )

    db.add(gps_log)
    db.commit()


# =========================
# HUB ALERTS (coordinator_admin / superadmin / admin)
#
# Surfaces trips that were started away from any hub's GPS range. The
# underlying event is already recorded at the moment a trip starts --
# see checkout_trip() in app/api/driver/trips.py, which sets
# Trip.started_outside_hub_range and inserts a
# Notification(type="STARTED_OUTSIDE_HUB_RANGE") row when that happens.
# These two endpoints just let trip managers list and acknowledge those
# rows, instead of only seeing the passive "⚠ Outside Hub" badge on the
# Active Trips Monitoring page.
# =========================
@router.get("/hub-alerts")
def get_hub_alerts(
    db: Session = Depends(get_db),
    current_admin=Depends(require_role_or_module(roles=["admin", "superadmin", "coordinator_admin"], module_key="trip_management.trips")),
):
    """Pending (not yet acknowledged) "started outside hub range" alerts,
    newest first. The frontend polls this on an interval to drive a
    notification badge/toast for coordinator_admin and superadmin."""

    alerts = (
        db.query(Notification)
        .filter(
            Notification.type == "STARTED_OUTSIDE_HUB_RANGE",
            Notification.status == "PENDING",
        )
        .order_by(Notification.created_at.desc())
        .all()
    )

    # Notification has no ORM relationships to Trip/User (see
    # app/models/notification.py), so trip/driver details are looked up
    # in one batch query each rather than per-row, to avoid N+1 queries.
    trip_ids = [a.trip_id for a in alerts if a.trip_id]
    trips_by_id = {
        t.id: t
        for t in db.query(Trip).filter(Trip.id.in_(trip_ids)).all()
    }

    return [
        {
            "id": alert.id,
            "trip_id": alert.trip_id,
            "driver_id": alert.driver_id,
            "message": alert.message,
            "ticket_no": (
                trips_by_id[alert.trip_id].ticket_no
                if alert.trip_id in trips_by_id
                else None
            ),
            "created_at": (
                utc_to_ph(alert.created_at).strftime("%Y-%m-%d %I:%M:%S %p")
                if alert.created_at
                else None
            ),
        }
        for alert in alerts
    ]


@router.post("/hub-alerts/{notification_id}/acknowledge")
def acknowledge_hub_alert(
    notification_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(require_role_or_module(roles=["admin", "superadmin", "coordinator_admin"], module_key="trip_management.trips")),
):
    """Dismisses one hub alert once a trip manager has seen/handled it,
    so it stops showing up in get_hub_alerts() and the notification
    badge count."""

    alert = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.type == "STARTED_OUTSIDE_HUB_RANGE",
        )
        .first()
    )

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")

    alert.status = "ACKNOWLEDGED"
    alert.reviewed_by_admin_id = current_admin.id
    alert.reviewed_at = datetime.utcnow()

    db.commit()

    return {"message": "Alert acknowledged."}

    return {"message": "Location tracked"}