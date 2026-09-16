# app/api/admin/trip_bypass.py
#
# "Trip Bypass" -- lets superadmin (always) or a specifically granted
# employee (Module Assignment -> trip_management.trip_bypass_actions)
# act as a driver on a trip that's stuck: perform whatever step the
# driver missed (forgot to upload a POD photo, lost their phone mid-trip,
# etc.) so the trip can keep moving instead of being stuck forever.
#
# Distinct from Trip Assignment (app/api/driver/trips.py's dispatch_trip),
# which is the office's normal "start a trip for a driver" step 0 -- this
# operates on a trip already in progress, and deliberately relaxes the
# ownership and geofence checks a real driver's own phone would hit,
# since an admin doing this from the office can never physically be at
# the location. Every action is logged to tpc_trip_bypass_logs with a
# required reason, since each one is overriding a safety check.

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.user import User
from app.models.trips import Trip, TripStatus
from app.models.trip_stops import TripStop, StopStatus
from app.models.stores import Store
from app.models.files import File as FileModel
from app.models.gps_log import GPSLog
from app.models.trip_models import GPSActionType
from app.models.trip_bypass_log import TripBypassLog
from app.services.file_service import FileService
from app.services.gps_service import calculate_distance_meters
from app.services.notification_service import create_notification
from app.api.driver.trips import _load_planned_store_ids, _delivered_store_ids

router = APIRouter(prefix="/admin/trips/bypass", tags=["Trip Bypass"])

_require_bypass_access = require_role_or_module(
    roles=["superadmin"], module_key="trip_management.trip_bypass_actions"
)


def _geofence_label(store, distance: float | None = None) -> str | None:
    if not store:
        return None
    label = store.name
    if distance is not None and distance != float("inf"):
        label += f" ({int(distance)}m)"
    return label


def _log_bypass(db: Session, trip_id: int, action: str, user_id: int, reason: str, stop_id: int | None = None):
    db.add(
        TripBypassLog(
            trip_id=trip_id,
            stop_id=stop_id,
            action=action,
            performed_by_user_id=user_id,
            reason=reason,
        )
    )


def _get_trip(db: Session, trip_id: int) -> Trip:
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return trip


def _get_open_stop(db: Session, trip_id: int) -> TripStop | None:
    return (
        db.query(TripStop)
        .filter(TripStop.trip_id == trip_id, TripStop.status != StopStatus.DELIVERED)
        .order_by(TripStop.id.desc())
        .first()
    )


# =========================
# LIST DRIVERS WITH AN IN-PROGRESS TRIP
# =========================
@router.get("/drivers")
def list_bypassable_trips(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_bypass_access),
):
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.driver), joinedload(Trip.destination_store))
        .filter(Trip.status.in_([TripStatus.ASSIGNED, TripStatus.ACTIVE]))
        .order_by(Trip.created_at.desc())
        .all()
    )

    return [
        {
            "trip_id": trip.id,
            "driver_id": trip.driver_id,
            "driver_name": trip.driver.username if trip.driver else None,
            "status": trip.status.value,
            "current_step": trip.current_step,
            "ticket_no": trip.ticket_no,
            "destination_store": (
                trip.destination_store.name if trip.destination_store else None
            ),
            "created_at": trip.created_at,
        }
        for trip in trips
    ]


# =========================
# TRIP DETAIL (trip + stops, for the bypass UI to figure out what's next)
# =========================
@router.get("/{trip_id}")
def get_bypass_trip_detail(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_bypass_access),
):
    trip = _get_trip(db, trip_id)

    stops = (
        db.query(TripStop)
        .options(joinedload(TripStop.store))
        .filter(TripStop.trip_id == trip_id)
        .order_by(TripStop.id.asc())
        .all()
    )

    planned_ids = _load_planned_store_ids(trip)
    delivered_ids = _delivered_store_ids(db, trip.id) if planned_ids else set()
    planned_stores_by_id = (
        {
            store.id: store
            for store in db.query(Store).filter(Store.id.in_(planned_ids)).all()
        }
        if planned_ids
        else {}
    )

    return {
        "trip_id": trip.id,
        "driver_id": trip.driver_id,
        "driver_name": trip.driver.username if trip.driver else None,
        "status": trip.status.value,
        "current_step": trip.current_step,
        "ticket_no": trip.ticket_no,
        "origin_store_id": trip.origin_store_id,
        "origin_store": trip.origin_store.name if trip.origin_store else None,
        "destination_store_id": trip.destination_store_id,
        "destination_store": (
            trip.destination_store.name if trip.destination_store else None
        ),
        "planned_stores": [
            {
                "store_id": sid,
                "store_name": (
                    planned_stores_by_id[sid].name
                    if sid in planned_stores_by_id
                    else None
                ),
                "delivered": sid in delivered_ids,
            }
            for sid in planned_ids
        ],
        "odometer_reading": trip.odometer_reading,
        "stops": [
            {
                "stop_id": stop.id,
                "store_id": stop.store_id,
                "store": stop.store.name if stop.store else None,
                "status": stop.status.value,
                "requires_review": stop.requires_review,
                "check_in_time": stop.check_in_time,
                "check_out_time": stop.check_out_time,
            }
            for stop in stops
        ],
    }


# =========================
# CHECKOUT (mirrors driver checkout_trip)
# =========================
@router.post("/{trip_id}/checkout")
def bypass_checkout(
    trip_id: int,
    reason: str = Form(...),
    odometer_reading: int = Form(0),
    invoice_photo: UploadFile | None = File(None),
    lm_photo: UploadFile | None = File(None),
    lm_checkout_stamped_photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_bypass_access),
):
    """Destination store(s) are already set on the trip from dispatch
    (Trip.planned_store_ids) -- this bypass step only needs the odometer
    reading and the same three photos the real Checkout step collects."""
    trip = _get_trip(db, trip_id)
    if trip.status != TripStatus.ASSIGNED:
        raise HTTPException(status_code=400, detail="Trip is not in ASSIGNED status.")

    destination_store = trip.destination_store

    file_service = FileService()

    if invoice_photo is not None:
        invoice_url = file_service.upload_trip_checkout_invoice(
            invoice_photo, trip.id,
            geofence_label=_geofence_label(destination_store),
            lat=destination_store.latitude if destination_store else None,
            long=destination_store.longitude if destination_store else None,
        )
        db.add(FileModel(
            entity_type="trip", entity_id=trip.id, document_type="INVOICE_PHOTO",
            file_url=invoice_url, uploaded_by=current_user.id,
        ))

    if lm_photo is not None:
        lm_url = file_service.upload_trip_checkout_lm(
            lm_photo, trip.id,
            geofence_label=_geofence_label(destination_store),
            lat=destination_store.latitude if destination_store else None,
            long=destination_store.longitude if destination_store else None,
        )
        db.add(FileModel(
            entity_type="trip", entity_id=trip.id, document_type="LM_MANIFEST_PHOTO",
            file_url=lm_url, uploaded_by=current_user.id,
        ))

    if lm_checkout_stamped_photo is not None:
        lm_stamped_url = file_service.upload_trip_checkout_lm_stamped(
            lm_checkout_stamped_photo, trip.id,
            geofence_label=_geofence_label(destination_store),
            lat=destination_store.latitude if destination_store else None,
            long=destination_store.longitude if destination_store else None,
        )
        db.add(FileModel(
            entity_type="trip", entity_id=trip.id,
            document_type="LM_CHECKOUT_STAMPED_PHOTO",
            file_url=lm_stamped_url, uploaded_by=current_user.id,
        ))

    trip.odometer_reading = odometer_reading
    trip.status = TripStatus.ACTIVE
    trip.current_step = "IN_TRANSIT"
    trip.start_time = datetime.utcnow()

    _log_bypass(db, trip.id, "checkout", current_user.id, reason)
    db.commit()

    return {"message": "Checkout completed (bypass). Trip started."}


# =========================
# CHECK-IN (arrival at a store) -- admin picks the store explicitly
# instead of GPS-resolving it, and the store's own registered
# coordinates become this stop's "arrival" position.
# =========================
@router.post("/{trip_id}/check-in")
def bypass_check_in(
    trip_id: int,
    reason: str = Form(...),
    store_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_bypass_access),
):
    trip = _get_trip(db, trip_id)
    if trip.status != TripStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Trip is not ACTIVE.")

    if _get_open_stop(db, trip.id):
        raise HTTPException(
            status_code=400, detail="This trip already has an open (non-delivered) stop."
        )

    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=400, detail="Store not found.")

    stop = TripStop(
        trip_id=trip.id,
        store_id=store.id,
        status=StopStatus.CHECKED_IN,
        check_in_time=datetime.utcnow(),
        lat_in=store.latitude,
        long_in=store.longitude,
        requires_review=False,
    )
    db.add(stop)
    db.flush()

    trip.current_step = "ARRIVED"

    _log_bypass(db, trip.id, "check-in", current_user.id, reason, stop_id=stop.id)
    db.commit()

    return {"message": "Checked in (bypass).", "stop_id": stop.id, "store": store.name}


# =========================
# START UNLOADING
# =========================
@router.post("/{trip_id}/stops/{stop_id}/start-unloading")
def bypass_start_unloading(
    trip_id: int,
    stop_id: int,
    reason: str = Form(...),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_bypass_access),
):
    stop = (
        db.query(TripStop)
        .filter(TripStop.id == stop_id, TripStop.trip_id == trip_id)
        .first()
    )
    if not stop:
        raise HTTPException(status_code=404, detail="Stop not found.")
    if stop.status != StopStatus.CHECKED_IN:
        raise HTTPException(status_code=400, detail="Stop must be checked in first.")

    trip = _get_trip(db, trip_id)

    stop.status = StopStatus.UNLOADING
    trip.current_step = "UNLOADING"
    db.flush()

    if photo is not None:
        file_service = FileService()
        photo_url = file_service.upload_trip_unloading_photo(
            photo, trip_id, stop.id, lat=stop.lat_in, long=stop.long_in,
        )
        db.add(FileModel(
            entity_type="trip_stop", entity_id=stop.id, document_type="UNLOADING_PHOTO",
            file_url=photo_url, uploaded_by=current_user.id,
        ))

    _log_bypass(db, trip_id, "start-unloading", current_user.id, reason, stop_id=stop.id)
    db.commit()

    return {"message": "Unloading started (bypass)."}


# =========================
# CHECK-OUT / POD -- the flagship case ("driver arrived but forgot to
# upload POD"). Reuses the stop's own recorded arrival coordinates
# (lat_in/long_in, "the same geofence used in the arrived store") instead
# of requiring fresh GPS, since the admin can't physically be there.
# =========================
@router.post("/{trip_id}/stops/{stop_id}/check-out")
def bypass_check_out(
    trip_id: int,
    stop_id: int,
    reason: str = Form(...),
    proof_photo: UploadFile | None = File(None),
    store_id: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_bypass_access),
):
    stop = (
        db.query(TripStop)
        .filter(TripStop.id == stop_id, TripStop.trip_id == trip_id)
        .first()
    )
    if not stop:
        raise HTTPException(status_code=404, detail="Stop not found.")
    if stop.status != StopStatus.UNLOADING:
        raise HTTPException(status_code=400, detail="Stop must be in unloading first.")

    # If the stop wasn't matched to a store at check-in (requires_review),
    # let the admin fix that here rather than leaving it orphaned.
    if store_id is not None:
        store = db.query(Store).filter(Store.id == store_id).first()
        if not store:
            raise HTTPException(status_code=400, detail="Store not found.")
        stop.store_id = store.id
        stop.requires_review = False
    else:
        store = db.query(Store).filter(Store.id == stop.store_id).first() if stop.store_id else None

    lat = stop.lat_in if stop.lat_in is not None else (store.latitude if store else None)
    long = stop.long_in if stop.long_in is not None else (store.longitude if store else None)

    distance = None
    if store and lat is not None and long is not None:
        distance = calculate_distance_meters(lat, long, store.latitude, store.longitude)

    stop.status = StopStatus.DELIVERED
    stop.check_out_time = datetime.utcnow()
    stop.lat_out = lat
    stop.long_out = long

    trip = _get_trip(db, trip_id)
    trip.current_step = "DELIVERED"
    db.flush()

    if proof_photo is not None:
        file_service = FileService()
        photo_url = file_service.upload_trip_pod_photo(
            proof_photo, trip_id=trip_id, stop_id=stop.id,
            geofence_label=_geofence_label(store, distance),
            lat=lat, long=long,
        )
        db.add(FileModel(
            entity_type="trip_stop", entity_id=stop.id, document_type="DELIVERY_PROOF_PHOTO",
            file_url=photo_url, uploaded_by=current_user.id,
        ))

    _log_bypass(db, trip_id, "check-out", current_user.id, reason, stop_id=stop.id)
    db.commit()

    return {"message": "Delivered (bypass)."}


# =========================
# CHECKIN (final step -- back at hub). Skips the hard hub-geofence block
# entirely (there's no prior "arrival" checkpoint to reuse the way
# check-out does) -- releases the vehicle/helpers, same as the real flow.
# =========================
@router.post("/{trip_id}/checkin")
def bypass_checkin(
    trip_id: int,
    reason: str = Form(...),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_bypass_access),
):
    trip = _get_trip(db, trip_id)
    if trip.status != TripStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Trip is not ACTIVE.")

    if _get_open_stop(db, trip.id):
        raise HTTPException(
            status_code=400, detail="Current stop must be delivered first."
        )

    hub = trip.origin_store
    lat = hub.latitude if hub else None
    long = hub.longitude if hub else None

    completion_time = datetime.utcnow()

    trip.status = TripStatus.PENDING_APPROVAL
    trip.current_step = "CHECKIN"
    trip.end_time = completion_time

    if lat is not None and long is not None:
        db.add(GPSLog(
            trip_id=trip.id, trip_stop_id=None, action_type=GPSActionType.TRACK,
            actual_lat=lat, actual_long=long, created_at=completion_time,
        ))

    for trip_helper in trip.trip_helpers:
        trip_helper.helper.is_available = 1

    if trip.vehicle_unit:
        trip.vehicle_unit.is_available = True

    db.flush()

    if photo is not None:
        file_service = FileService()
        photo_url = file_service.upload_trip_end_photo(
            photo, trip.id, geofence_label=_geofence_label(hub), lat=lat, long=long,
        )
        db.add(FileModel(
            entity_type="trip", entity_id=trip.id, document_type="STAMPED_INVOICE_PHOTO",
            file_url=photo_url, uploaded_by=current_user.id,
        ))

    create_notification(
        db=db, type_="TRIP_COMPLETED", driver_id=trip.driver_id, trip_id=trip.id,
        message=f"Trip completed via admin bypass and awaiting approval. Reason: {reason}",
    )

    _log_bypass(db, trip.id, "checkin", current_user.id, reason)
    db.commit()

    return {"message": "Trip completed and submitted for approval (bypass)."}
