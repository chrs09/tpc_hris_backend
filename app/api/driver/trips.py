# app/api/driver/trips.py

import json
import traceback
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import List

from app.core.database import get_db
from app.utils.response import api_response
from app.schemas.trip import LocationRequest
from app.core.dependencies import get_current_user
from app.models.trips import Trip, TripStatus
from app.models.trip_stops import TripStop, StopStatus
from app.models.stores import Store
from app.models.trip_helper import TripHelper
from app.models.employees import Employee
from app.models.files import File as FileModel
from app.services.file_service import FileService
from app.models.gps_log import GPSLog
from app.models.trip_models import GPSActionType
from app.services.gps_service import calculate_distance_meters
from app.services.notification_service import create_notification

router = APIRouter(prefix="/driver/trips", tags=["Driver Trips"])

HUB_NAMES = {"Yard", "Plant", "Consolacion", "Test Hub"}
logger = logging.getLogger("driver.trips")

class StartTripRequest(BaseModel):
    lat: float
    long: float
    ticket_no: str
    helper_ids: List[int] = []


class CheckInRequest(BaseModel):
    lat: float
    long: float


class AddHelperRequest(BaseModel):
    helper_ids: List[int]

class TrackLocationRequest(BaseModel):
    lat: float
    long: float
    accuracy: float | None = None
    speed: float | None = None
    created_at: datetime | None = None


# =========================
# GET AVAILABLE HELPERS
# =========================
@router.get("/available-helpers")
def get_available_helpers(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # ---------------------------------------
    # 1️⃣ Get Driver Employee Record
    # ---------------------------------------
    driver_employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
    )

    if not driver_employee:
        raise HTTPException(status_code=400, detail="Driver employee record not found.")

    # ---------------------------------------
    # 2️⃣ Determine Allowed Helper Department
    # ---------------------------------------
    if driver_employee.department == "CpdcDriver":
        required_department = "CpdcHelper"
    elif driver_employee.department == "CdcDriver":
        required_department = "CdcHelper"
    else:
        # Driver not eligible for helpers
        return []

    # ---------------------------------------
    # 3️⃣ Get Available Helpers
    # ---------------------------------------
    helpers = (
        db.query(Employee)
        .filter(
            Employee.position == "HELPER",
            Employee.department == required_department,
            Employee.is_active == 1,
            Employee.is_available == 1,
        )
        .all()
    )

    # ---------------------------------------
    # 4️⃣ Return Clean Response
    # ---------------------------------------
    return [
        {
            "id": helper.id,
            "first_name": helper.first_name,
            "last_name": helper.last_name,
            "department": helper.department,
        }
        for helper in helpers
    ]


# =========================
# GET ACTIVE TRIP
# =========================
@router.get("/active")
def get_active_trip(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # =========================
    # 1️⃣ Get Active Trip
    # =========================
    trip = (
        db.query(Trip)
        .filter(
            Trip.driver_id == current_user.id,
            Trip.status == TripStatus.ACTIVE,
        )
        .first()
    )

    if not trip:
        return {
            "active_trip": None,
            "latest_stop": None,
            "has_open_stop": False,
        }

    # =========================
    # 2️⃣ Get Origin Store
    # =========================
    origin_store = (
        db.query(Store)
        .filter(Store.id == trip.origin_store_id)
        .first()
    )

    # =========================
    # 3️⃣ Get Latest Stop
    # =========================
    latest_stop = (
        db.query(TripStop)
        .filter(TripStop.trip_id == trip.id)
        .order_by(TripStop.id.desc())
        .first()
    )

    has_open_stop = (
        True if latest_stop and latest_stop.status == StopStatus.CHECKED_IN else False
    )

    # =========================
    # 4️⃣ Build Latest Stop Data
    # =========================
    latest_stop_data = None

    if latest_stop:
        stop_store = None

        if latest_stop.store_id:
            stop_store = (
                db.query(Store)
                .filter(Store.id == latest_stop.store_id)
                .first()
            )

        latest_stop_data = {
            "id": latest_stop.id,
            "trip_id": latest_stop.trip_id,
            "store_id": latest_stop.store_id,
            "store_name": stop_store.name if stop_store else "Unknown Location",

            "status": latest_stop.status.value
            if hasattr(latest_stop.status, "value")
            else latest_stop.status,

            "check_in_time": latest_stop.check_in_time,
            "check_out_time": latest_stop.check_out_time,

            "lat_in": latest_stop.lat_in,
            "long_in": latest_stop.long_in,
            "lat_out": latest_stop.lat_out,
            "long_out": latest_stop.long_out,

            "requires_review": latest_stop.requires_review,
            "created_at": latest_stop.created_at,
        }

    # =========================
    # 5️⃣ Build Active Trip Data
    # =========================
    active_trip_data = {
        "id": trip.id,
        "driver_id": trip.driver_id,
        "ticket_no": trip.ticket_no,

        "status": trip.status.value
        if hasattr(trip.status, "value")
        else trip.status,

        "origin_store_id": trip.origin_store_id,
        "origin_name": origin_store.name if origin_store else "N/A",

        "start_time": trip.start_time,
        "end_time": trip.end_time,
        "created_at": trip.created_at,
    }

    # =========================
    # 6️⃣ Final Response
    # =========================
    return {
        "active_trip": active_trip_data,
        "latest_stop": latest_stop_data,
        "has_open_stop": has_open_stop,
    }


# =========================
# START TRIP
# =========================
@router.post("/start")
def start_trip(
    ticket_no: str = Form(...),
    lat: float = Form(...),
    long: float = Form(...),
    photo: UploadFile = File(...),
    helper_ids: str = Form("[]"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):

    helper_ids = json.loads(helper_ids)

    # ---------------------------------------
    # 1️⃣ Prevent multiple ACTIVE trips
    # ---------------------------------------
    existing_active = (
        db.query(Trip)
        .filter(Trip.driver_id == current_user.id, Trip.status == TripStatus.ACTIVE)
        .first()
    )

    if existing_active:
        raise HTTPException(status_code=400, detail="You already have an active trip.")

    # ---------------------------------------
    # 2️⃣ Validate ticket
    # ---------------------------------------
    if not ticket_no or not ticket_no.strip():
        raise HTTPException(status_code=400, detail="Ticket number is required.")

    existing_ticket = db.query(Trip).filter(Trip.ticket_no == ticket_no).first()

    if existing_ticket:
        raise HTTPException(status_code=400, detail="Ticket number already exists.")

    # ---------------------------------------
    # 3️⃣ Validate Origin GPS
    # ---------------------------------------
    stores = db.query(Store).all()

    closest_store = None
    min_distance = float("inf")

    for store in stores:

        distance = calculate_distance_meters(lat, long, store.latitude, store.longitude)

        if distance <= store.allowed_radius_meters and distance < min_distance:
            min_distance = distance
            closest_store = store

    if not closest_store:
        raise HTTPException(
            status_code=400, detail="You must start the trip from a valid hub location."
        )

    # ---------------------------------------
    # 4️⃣ Validate Helpers
    # ---------------------------------------
    if len(helper_ids) > 3:
        raise HTTPException(status_code=400, detail="Maximum of 3 helpers allowed.")

    driver_employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
    )

    if not driver_employee:
        raise HTTPException(status_code=400, detail="Driver employee not found.")

    if driver_employee.department == "CpdcDriver":
        required_department = "CpdcHelper"

    elif driver_employee.department == "CdcDriver":
        required_department = "CdcHelper"

    else:
        raise HTTPException(status_code=400, detail="Driver not eligible for helpers.")

    helper_objects = []

    for helper_id in helper_ids:

        helper = db.query(Employee).filter(Employee.id == helper_id).first()

        if not helper:
            raise HTTPException(
                status_code=404, detail=f"Helper {helper_id} not found."
            )

        if helper.position != "Helper":
            raise HTTPException(status_code=400, detail="Invalid helper position.")

        if helper.department != required_department:
            raise HTTPException(status_code=400, detail="Helper department mismatch.")

        if not helper.is_available:
            raise HTTPException(
                status_code=400, detail=f"{helper.first_name} is unavailable."
            )

        helper_objects.append(helper)

    # ---------------------------------------
    # 5️⃣ Create Trip + Upload Photo
    # ---------------------------------------
    try:

        new_trip = Trip(
            driver_id=current_user.id,
            origin_store_id=closest_store.id,
            ticket_no=ticket_no.strip(),
            status=TripStatus.ACTIVE,
            start_time=datetime.utcnow(),
        )

        db.add(new_trip)
        db.flush()

        # Upload start photo
        file_service = FileService()

        photo_url = file_service.upload_trip_start_photo(photo, new_trip.id)

        trip_file = FileModel(
            entity_type="trip",
            entity_id=new_trip.id,
            document_type="START_TRIP_PHOTO",
            file_url=photo_url,
            uploaded_by=current_user.id,
        )

        db.add(trip_file)

        # Lock helpers
        for helper in helper_objects:

            helper.is_available = 0

            trip_helper = TripHelper(trip_id=new_trip.id, helper_id=helper.id)

            db.add(trip_helper)

        db.commit()

    except Exception as e:
        print("START TRIP ERROR:", e)
        db.rollback()

        raise HTTPException(status_code=500, detail="Failed to start trip.")

    return {
        "message": "Trip started successfully.",
        "trip_id": new_trip.id,
        "origin": closest_store.name,
        "helpers_assigned": len(helper_objects),
    }


# =========================
# CHECK-IN
# =========================
@router.post("/{trip_id}/check-in")
def check_in(
    trip_id: int,
    payload: LocationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # ---------------------------------------
    # 1️⃣ Validate Trip Ownership & Status
    # ---------------------------------------
    trip = (
        db.query(Trip)
        .filter(
            Trip.id == trip_id,
            Trip.driver_id == current_user.id,
            Trip.status == TripStatus.ACTIVE,
        )
        .first()
    )

    if not trip:
        raise HTTPException(status_code=404, detail="Active trip not found.")

    # ---------------------------------------
    # 2️⃣ Prevent Multiple Open Stops
    # ---------------------------------------
    open_stop = (
        db.query(TripStop)
        .filter(TripStop.trip_id == trip.id, TripStop.status == StopStatus.CHECKED_IN)
        .first()
    )

    if open_stop:
        raise HTTPException(
            status_code=400, detail="You must check out from current stop first."
        )

    # ---------------------------------------
    # 3️⃣ Prevent Immediate Duplicate Check-In
    # ---------------------------------------
    last_stop = (
        db.query(TripStop)
        .filter(TripStop.trip_id == trip.id)
        .order_by(TripStop.id.desc())
        .first()
    )

    if last_stop and last_stop.status == StopStatus.CHECKED_OUT:
        if last_stop.lat_out is not None and last_stop.long_out is not None:

            distance_from_last = calculate_distance_meters(
                payload.lat, payload.long, last_stop.lat_out, last_stop.long_out
            )

            if distance_from_last < 50:  # 50 meters threshold
                raise HTTPException(
                    status_code=400, detail="Already checked out from this location."
                )

    # ---------------------------------------
    # 4️⃣ Find Closest Registered Store
    # ---------------------------------------
    stores = db.query(Store).all()

    closest_store = None
    min_distance = float("inf")

    for store in stores:
        distance = calculate_distance_meters(
            payload.lat, payload.long, store.latitude, store.longitude
        )

        if distance <= store.allowed_radius_meters and distance < min_distance:
            min_distance = distance
            closest_store = store

    # ---------------------------------------
    # 5️⃣ Create Trip Stop
    # ---------------------------------------
    stop = TripStop(
        trip_id=trip.id,
        store_id=closest_store.id if closest_store else None,
        status=StopStatus.CHECKED_IN,
        check_in_time=datetime.utcnow(),
        lat_in=payload.lat,
        long_in=payload.long,
        requires_review=(closest_store is None),
    )

    db.add(stop)
    db.flush()  # Get stop.id before commit

    # ---------------------------------------
    # 6️⃣ Notify Admin if Unknown Location
    # ---------------------------------------
    if not closest_store:
        create_notification(
            db=db,
            type_="UNREGISTERED_STORE",
            driver_id=current_user.id,
            trip_id=trip.id,
            trip_stop_id=stop.id,
            message="Driver checked in at unknown location.",
        )

    db.commit()

    return {
        "message": "Checked in successfully.",
        "store": closest_store.name if closest_store else "Unknown Location",
        "requires_review": stop.requires_review,
    }


# =========================
# CHECK-OUT
# =========================
@router.post("/{trip_id}/check-out/{stop_id}")
def check_out(
    trip_id: int,
    stop_id: int,
    payload: LocationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):

    stop = (
        db.query(TripStop)
        .filter(TripStop.id == stop_id, TripStop.trip_id == trip_id)
        .first()
    )

    if not stop:
        raise HTTPException(status_code=404, detail="Stop not found")

    if stop.status != StopStatus.CHECKED_IN:
        raise HTTPException(status_code=400, detail="Must check-in first")

    # if lat_out and long_out not matches the lat_in and long_in, then reject the check-out
    distance = calculate_distance_meters(
        payload.lat, payload.long, stop.lat_in, stop.long_in
    )
    if distance > 150:
        raise HTTPException(
            status_code=400,
            detail="Check-out location is too far from check-in location.",
        )

    stop.status = StopStatus.CHECKED_OUT
    stop.check_out_time = datetime.utcnow()
    stop.lat_out = payload.lat
    stop.long_out = payload.long

    db.commit()

    return {"message": "Checked out successfully."}

# =========================
# TRACK TRIP LOCATION
# =========================
@router.post("/{trip_id}/track")
def track_trip_location(
    trip_id: int,
    payload: TrackLocationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Validate trip
    trip = (
        db.query(Trip)
        .filter(
            Trip.id == trip_id,
            Trip.driver_id == current_user.id,
            Trip.status == TripStatus.ACTIVE,
        )
        .first()
    )

    if not trip:
        raise HTTPException(status_code=404, detail="Active trip not found.")

    gps_log = GPSLog(
        trip_id=trip.id,
        trip_stop_id=None,
        action_type=GPSActionType.TRACK,
        actual_lat=payload.lat,
        actual_long=payload.long,
        accuracy=payload.accuracy,
        speed=payload.speed,
        created_at=payload.created_at or datetime.utcnow(),
    )

    db.add(gps_log)
    db.commit()

    logger.info(
        "[TRACK] trip_id=%s lat=%s long=%s accuracy=%s speed=%s created_at=%s",
        trip.id,
        payload.lat,
        payload.long,
        payload.accuracy,
        payload.speed,
        payload.created_at,
    )

    return {"message": "Tracking saved"}


# =========================
# COMPLETE TRIP
# =========================
@router.post("/{trip_id}/complete")
def complete_trip(
    trip_id: int,
    payload: LocationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # ---------------------------------------
    # 1️⃣ Validate Trip Ownership & Status
    # ---------------------------------------
    trip = (
        db.query(Trip)
        .filter(
            Trip.id == trip_id,
            Trip.driver_id == current_user.id,
            Trip.status == TripStatus.ACTIVE,
        )
        .first()
    )

    if not trip:
        raise HTTPException(status_code=404, detail="Active trip not found.")

    # ---------------------------------------
    # 2️⃣ Prevent Completion If Stop Still Open
    # ---------------------------------------
    open_stop = (
        db.query(TripStop)
        .filter(TripStop.trip_id == trip.id, TripStop.status == StopStatus.CHECKED_IN)
        .first()
    )

    if open_stop:
        raise HTTPException(
            status_code=400,
            detail="You must check out from current stop before completing trip.",
        )

    # ---------------------------------------
    # 3️⃣ Validate GPS Against Allowed Hub Names
    # ---------------------------------------
    hub_stores = db.query(Store).filter(Store.name.in_(HUB_NAMES)).all()

    if not hub_stores:
        raise HTTPException(
            status_code=500, detail="Hub locations not configured in system."
        )

    valid_hub = None
    min_distance = float("inf")

    for store in hub_stores:
        distance = calculate_distance_meters(
            payload.lat, payload.long, store.latitude, store.longitude
        )

        if distance <= store.allowed_radius_meters and distance < min_distance:
            min_distance = distance
            valid_hub = store

    if not valid_hub:
        raise HTTPException(
            status_code=400,
            detail="You must return to Yard, Plant, or Consolacion to complete trip.",
        )

    # ---------------------------------------
    # 4️⃣ Complete Trip
    # ---------------------------------------
    trip.status = TripStatus.PENDING_APPROVAL
    trip.end_time = datetime.utcnow()

    for trip_helper in trip.trip_helpers:
        trip_helper.helper.is_available = 1

    # ---------------------------------------
    # 5️⃣ Notify Admin
    # ---------------------------------------
    create_notification(
        db=db,
        type_="TRIP_COMPLETED",
        driver_id=current_user.id,
        trip_id=trip.id,
        message=f"Trip completed at {valid_hub.name} and awaiting admin approval.",
    )

    db.commit()

    return {"message": "Trip submitted for approval.", "completed_at": valid_hub.name}


# =========================
# TRIP HELPERS
# =========================
@router.post("/{trip_id}/helpers")
def add_helpers_to_trip(
    trip_id: int,
    payload: AddHelperRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # ---------------------------------------
    # 1️⃣ Validate Trip
    # ---------------------------------------
    trip = (
        db.query(Trip)
        .filter(
            Trip.id == trip_id,
            Trip.driver_id == current_user.id,
            Trip.status == TripStatus.ACTIVE,
        )
        .first()
    )

    if not trip:
        raise HTTPException(status_code=404, detail="Active trip not found.")

    # ---------------------------------------
    # 2️⃣ Validate Max 3 Helpers
    # ---------------------------------------
    if len(payload.helper_ids) == 0:
        raise HTTPException(status_code=400, detail="No helpers selected.")

    if len(payload.helper_ids) > 3:
        raise HTTPException(status_code=400, detail="Maximum of 3 helpers allowed.")

    # ---------------------------------------
    # 3️⃣ Prevent Duplicate Assignment
    # ---------------------------------------
    existing_count = db.query(TripHelper).filter(TripHelper.trip_id == trip.id).count()

    if existing_count + len(payload.helper_ids) > 3:
        raise HTTPException(status_code=400, detail="Trip already has maximum helpers.")

    # ---------------------------------------
    # 4️⃣ Determine Allowed Helper Department
    # ---------------------------------------
    driver_employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
    )

    if not driver_employee:
        raise HTTPException(status_code=400, detail="Driver employee record not found.")

    if driver_employee.department == "CpdcDriver":
        required_department = "CpdcHelper"
    elif driver_employee.department == "CdcDriver":
        required_department = "CdcHelper"
    else:
        raise HTTPException(
            status_code=400,
            detail="Driver department is not eligible for helper assignment.",
        )

    # ---------------------------------------
    # 5️⃣ Validate Each Helper
    # ---------------------------------------
    for helper_id in payload.helper_ids:

        helper = db.query(Employee).filter(Employee.id == helper_id).first()

        if not helper:
            raise HTTPException(
                status_code=404, detail=f"Helper ID {helper_id} not found."
            )

        if helper.position != "Helper":
            raise HTTPException(
                status_code=400, detail=f"{helper.first_name} is not a helper."
            )

        if helper.department != required_department:
            raise HTTPException(
                status_code=400,
                detail=f"{helper.first_name} does not belong to required department.",
            )

        if not helper.is_available:
            raise HTTPException(
                status_code=400, detail=f"{helper.first_name} is currently unavailable."
            )

        # Lock helper
        helper.is_available = 0

        # Create mapping
        trip_helper = TripHelper(trip_id=trip.id, helper_id=helper.id)

        db.add(trip_helper)

    db.commit()

    return {"message": "Helpers assigned successfully."}


# =========================
# DRIVER TRIP SUMMARY
# =========================
@router.get("/trip-summary")
def driver_trip_summary(
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):

    # Get PH current time
    now_ph = datetime.utcnow() + timedelta(hours=8)

    # PH start and end of day
    today_start_ph = datetime.combine(now_ph.date(), datetime.min.time())
    today_end_ph = datetime.combine(now_ph.date(), datetime.max.time())

    # Convert PH day → UTC for DB comparison
    today_start_utc = today_start_ph - timedelta(hours=8)
    today_end_utc = today_end_ph - timedelta(hours=8)

    base_query = db.query(Trip).filter(Trip.driver_id == current_user.id)

    active_count = base_query.filter(Trip.status == TripStatus.ACTIVE).count()

    pending_count = base_query.filter(
        Trip.status == TripStatus.PENDING_APPROVAL
    ).count()

    completed_today_count = base_query.filter(
        Trip.status == TripStatus.COMPLETED,
        Trip.end_time >= today_start_utc,
        Trip.end_time <= today_end_utc,
    ).count()

    total_completed_count = base_query.filter(
        Trip.status == TripStatus.COMPLETED
    ).count()

    return {
        "active_trips": active_count,
        "pending_trips": pending_count,
        "completed_today": completed_today_count,
        "total_completed": total_completed_count,
    }


# =========================
# GET DRIVER TRIPS LIST
# =========================
@router.get("/my-trips")
def get_my_trips(db: Session = Depends(get_db), current_user=Depends(get_current_user)):

    trips = (
        db.query(Trip)
        .filter(Trip.driver_id == current_user.id)
        .order_by(Trip.start_time.desc())
        .all()
    )

    results = []

    for trip in trips:
        results.append(
            {
                "id": trip.id,
                "ticket_no": trip.ticket_no,
                "status": trip.status.value
                if hasattr(trip.status, "value")
                else trip.status,
                "start_time": trip.start_time,
                "end_time": trip.end_time,
            }
        )

    return api_response(results)

# =========================
# DRIVER PROFILE
# =========================
@router.get("/profile")
def get_driver_profile(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # 1️⃣ Get employee record
    employee = (
        db.query(Employee)
        .filter(Employee.id == current_user.employee_id)
        .first()
    )

    if not employee:
        raise HTTPException(status_code=404, detail="Employee profile not found.")

    # 2️⃣ Build full name
    full_name = f"{employee.first_name} {employee.last_name}"

    # 3️⃣ Return combined data
    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,

        "employee_id": employee.id,
        "full_name": full_name,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "department": employee.department,
        "position": employee.position,
        "email": employee.email,
    }
