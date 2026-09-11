# app/api/driver/trips.py

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import List

from app.core.database import get_db
from app.utils.response import api_response
from app.schemas.trip import LocationRequest
from app.core.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.trips import Trip, TripStatus
from app.models.trip_finance_review import TripFinanceReview, FinanceReviewStatus
from app.models.trip_stops import TripStop, StopStatus
from app.models.stores import Store
from app.models.trip_helper import TripHelper
from app.models.employees import Employee
from app.models.files import File as FileModel
from app.services.file_service import FileService
from app.models.gps_log import GPSLog
from app.models.vehicle_unit import VehicleUnit
from app.models.TripRate import TripRateProfile
from app.models.trip_models import GPSActionType
from app.models.app_setting import AppSetting
from app.services.gps_service import calculate_distance_meters, find_nearest_store
from app.services.shipment_ocr_service import ShipmentOCRService
from app.services.notification_service import create_notification
from app.services.trip_payroll_service import (
    to_ph,
    now_ph,
    period_key,
    period_bounds,
    next_period_key,
    parse_cutoff_value,
)

router = APIRouter(prefix="/driver/trips", tags=["Driver Trips"])

# Roles that can start a trip on behalf of a driver instead of themselves
# (e.g. the driver checks in on their own phone afterward). Mirrors
# get_current_trip_manager in app/core/dependencies.py.
TRIP_MANAGER_ROLES = {"admin", "superadmin", "coordinator_admin"}


def _role_value(role) -> str:
    return role.value if hasattr(role, "value") else str(role)


def _geofence_label(store, distance: float | None, outside_range: bool = False) -> str | None:
    """A short "<place> (<distance>m)" label burned into a photo's
    watermark alongside the timestamp, so the stored image also carries a
    rough record of where it was taken."""
    if not store:
        return None
    label = store.name
    if distance is not None and distance != float("inf"):
        label += f" ({int(distance)}m)"
    if outside_range:
        label += " - outside range"
    return label


def _generate_trip_code(db: Session, start_time: datetime) -> str:
    """Auto-generated, human-readable trip reference: "YYYYMM-00001",
    sequential per PH-local calendar month (resets to 00001 each new
    month) -- distinct from Trip.id (the DB primary key) and
    Trip.ticket_no (freely typed, only known after Checkout). Reads the
    highest existing code for the month and increments it; the column's
    unique index is the real safety net against a collision under
    concurrent trip creation (would surface as a rare, retryable DB
    error rather than a silent duplicate) -- trip creation isn't
    frequent/concurrent enough here to warrant a dedicated counter
    table."""
    period = to_ph(start_time).strftime("%Y%m")
    prefix = f"{period}-"

    last_code = (
        db.query(Trip.trip_code)
        .filter(Trip.trip_code.like(f"{prefix}%"))
        .order_by(Trip.trip_code.desc())
        .first()
    )

    next_number = 1
    if last_code and last_code[0]:
        try:
            next_number = int(last_code[0].split("-")[1]) + 1
        except (IndexError, ValueError):
            next_number = 1

    return f"{prefix}{next_number:05d}"


def _helper_departments_for(driver_department: str | None) -> list[str]:
    """Which Employee.department values count as eligible helpers for a
    driver in the given department. CpdcDriver/CdcDriver each draw from
    their own dedicated helper department; every other driver department
    (WingvanDriver, Dumptruck, Motorpool, Labor, etc.) shares the combined
    Cdc/Cpdc helper pool instead of needing a department-specific one."""
    if driver_department == "CpdcDriver":
        return ["CpdcHelper"]
    if driver_department == "CdcDriver":
        return ["CdcHelper"]
    return ["CdcHelper", "CpdcHelper"]

# Hub/origin locations (yard, plant, satellite offices) used to be
# identified here by a hardcoded set of store names. They're now marked
# with Store.is_hub (see app/models/stores.py) and looked up with a plain
# `Store.is_hub.is_(True)` filter wherever this used to be referenced --
# see get_available_stores() and complete_trip() below.

# =========================
# DRIVER TRIP LOGGER
# =========================

BASE_DIR = Path(__file__).resolve().parents[3]

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("driver.trips")
logger.setLevel(logging.INFO)

if not logger.handlers:

    log_file = LOG_DIR / "driver_trip_tracking.log"

    handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    handler.setFormatter(formatter)

    logger.addHandler(handler)

    logger.propagate = False

# =========================
# GPS TRAFFIC BYTE LOGGER
# =========================

gps_traffic_logger = logging.getLogger("driver.gps_traffic")
gps_traffic_logger.setLevel(logging.INFO)

if not gps_traffic_logger.handlers:

    traffic_log_file = LOG_DIR / "gps_traffic.log"

    traffic_handler = RotatingFileHandler(
        traffic_log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )

    traffic_formatter = logging.Formatter(
        "%(asctime)s | %(message)s"
    )

    traffic_handler.setFormatter(traffic_formatter)

    gps_traffic_logger.addHandler(traffic_handler)

    gps_traffic_logger.propagate = False


# =========================
# WALLET DEBUG LOGGER (terminal, JSON)
# =========================
# Separate from `logger` above (which only writes to a file). This one
# prints a single JSON object per line straight to stdout so you can
# watch what the wallet endpoints matched/computed live in the terminal
# while testing, e.g.:
#   tail -f your_terminal | grep '"event": "wallet' (or just watch it scroll)
wallet_logger = logging.getLogger("driver.wallet")
wallet_logger.setLevel(logging.INFO)

if not wallet_logger.handlers:

    stream_handler = logging.StreamHandler(sys.stdout)

    # Bare message only -- we already put everything (timestamp included)
    # into the JSON payload itself, so the line stays valid/parseable JSON.
    stream_handler.setFormatter(logging.Formatter("%(message)s"))

    wallet_logger.addHandler(stream_handler)

    wallet_logger.propagate = False


def log_wallet_event(event: str, **fields):
    """Emit one JSON line to the terminal for wallet debugging."""
    payload = {
        "event": event,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **fields,
    }
    wallet_logger.info(json.dumps(payload, default=str))


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
    driver_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # ---------------------------------------
    # 1️⃣ Get Driver Employee Record
    #
    # driver_id is only honored for a trip manager looking up helpers on
    # behalf of a driver (see start_trip's bypass) -- a plain driver always
    # gets helpers for their own department regardless of what's passed.
    # ---------------------------------------
    employee_id = current_user.employee_id

    if driver_id and _role_value(current_user.role) in TRIP_MANAGER_ROLES:
        target_user = (
            db.query(User)
            .filter(User.id == driver_id, User.role == UserRole.DRIVER)
            .first()
        )
        if not target_user:
            raise HTTPException(status_code=400, detail="Selected driver not found.")
        employee_id = target_user.employee_id

    driver_employee = (
        db.query(Employee).filter(Employee.id == employee_id).first()
    )

    if not driver_employee:
        raise HTTPException(status_code=400, detail="Driver employee record not found.")

    # ---------------------------------------
    # 2️⃣ Determine Allowed Helper Department(s)
    # ---------------------------------------
    required_departments = _helper_departments_for(driver_employee.department)

    # ---------------------------------------
    # 3️⃣ Get Available Helpers
    # ---------------------------------------
    helpers = (
        db.query(Employee)
        .filter(
            Employee.position == "HELPER",
            Employee.department.in_(required_departments),
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
# GET AVAILABLE VEHICLE
# =========================
@router.get("/available-vehicles")
def get_available_vehicles(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):

    vehicles = (
        db.query(VehicleUnit)
        .filter(
            VehicleUnit.is_active.is_(True),
            VehicleUnit.is_available.is_(True),
        )
        .order_by(VehicleUnit.unit_code.asc())
        .all()
    )

    return [
        {
            "id": vehicle.id,
            "unit_code": vehicle.unit_code,
            "plate_number": vehicle.plate_number,
            "description": vehicle.description,
        }
        for vehicle in vehicles
    ]


# =========================
# GET TRIP RATES
# =========================
@router.get("/trip-rate-profiles")
def get_trip_rate_profiles(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):

    profiles = (
        db.query(TripRateProfile)
        .filter(TripRateProfile.is_active.is_(True))
        .order_by(TripRateProfile.profile_name.asc())
        .all()
    )

    return [
        {
            "id": profile.id,
            "profile_name": profile.profile_name,
            "helper_count": profile.helper_count,
        }
        for profile in profiles
    ]



# =========================
# GET AVAILABLE STORES
# =========================

@router.get("/available-stores")
def get_available_stores(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List stores a driver can pick as a delivery destination when
    starting a trip. Hub/origin locations (Store.is_hub) are excluded --
    a driver delivers TO a store, not to a hub, so hubs don't belong in
    this dropdown."""
    stores = db.query(Store).order_by(Store.name.asc()).all()

    results = []

    for store in stores:
        if store.is_hub:
            continue

        # Preferred path: direct FK, set by the migration/backfill or by
        # the updated create_store/update_store endpoints going forward.
        if store.trip_rate_profile_id and store.trip_rate_profile:
            profile = store.trip_rate_profile

            results.append(
                {
                    "id": store.id,
                    "name": store.name,
                    "latitude": store.latitude,
                    "longitude": store.longitude,
                    "allowed_radius_meters": store.allowed_radius_meters,
                    "trip_rate_profile_id": profile.id,
                    "profile_name": profile.profile_name,
                    "helper_count": store.required_helper,
                }
            )
            continue

        # Fallback path: legacy stores not yet backfilled. Remove this
        # branch once every store has trip_rate_profile_id populated
        # (check with the audit query in the migration notes).
        results.append(
            {
                "id": store.id,
                "name": store.name,
                "latitude": store.latitude,
                "longitude": store.longitude,
                "allowed_radius_meters": store.allowed_radius_meters,
                "trip_rate_profile_id": None,
                "profile_name": None,
                "helper_count": store.required_helper,
            }
        )

    return results
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
            Trip.status.in_([TripStatus.ASSIGNED, TripStatus.ACTIVE]),
        )
        .order_by(Trip.id.desc())
        .first()
    )

    if not trip:
        return {
            "active_trip": None,
            "latest_stop": None,
            "has_open_stop": False,
        }

    # =========================
    # 2️⃣ Get Origin / Destination Store
    # =========================
    origin_store = db.query(Store).filter(Store.id == trip.origin_store_id).first()
    destination_store = (
        db.query(Store).filter(Store.id == trip.destination_store_id).first()
        if trip.destination_store_id
        else None
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

    # A stop is "open" (blocks starting a new one) until it's been
    # marked DELIVERED -- CHECKED_IN and UNLOADING are both mid-visit.
    has_open_stop = (
        True
        if latest_stop and latest_stop.status != StopStatus.DELIVERED
        else False
    )

    # =========================
    # 4️⃣ Build Latest Stop Data
    # =========================
    latest_stop_data = None

    if latest_stop:
        stop_store = None

        if latest_stop.store_id:
            stop_store = (
                db.query(Store).filter(Store.id == latest_stop.store_id).first()
            )

        latest_stop_data = {
            "id": latest_stop.id,
            "trip_id": latest_stop.trip_id,
            "store_id": latest_stop.store_id,
            "store_name": stop_store.name if stop_store else "Unknown Location",
            "status": (
                latest_stop.status.value
                if hasattr(latest_stop.status, "value")
                else latest_stop.status
            ),
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
        "current_step": trip.current_step,
        "odometer_reading": trip.odometer_reading,
        "vehicle": (
            {
                "id": trip.vehicle_unit.id,
                "unit_code": trip.vehicle_unit.unit_code,
                "plate_number": trip.vehicle_unit.plate_number,
                "description": trip.vehicle_unit.description,
            }
            if trip.vehicle_unit
            else None
        ),
        "trip_rate_profile": (
            {
                "id": trip.trip_rate_profile.id,
                "profile_name": trip.trip_rate_profile.profile_name,
                "helper_count": trip.trip_rate_profile.helper_count,
                "driver_first_trip_rate": trip.trip_rate_profile.driver_first_trip_rate,
                "driver_next_trip_rate": trip.trip_rate_profile.driver_next_trip_rate,
            }
            if trip.trip_rate_profile
            else None
        ),
        "status": trip.status.value if hasattr(trip.status, "value") else trip.status,
        "origin_store_id": trip.origin_store_id,
        "origin_name": origin_store.name if origin_store else "N/A",
        "destination_store_id": trip.destination_store_id,
        "destination_name": destination_store.name if destination_store else None,
        "start_time": trip.start_time,
        "end_time": trip.end_time,
        "created_at": trip.created_at,
    }

    # =========================
    # 6️⃣ Final Response
    # =========================
    return api_response({
        "active_trip": active_trip_data,
        "latest_stop": latest_stop_data,
        "has_open_stop": has_open_stop,
    })


# =========================
# DISPATCH TRIP (coordinator-only -- assigns driver + vehicle + hub)
# =========================
@router.post("/dispatch")
def dispatch_trip(
    driver_id: int = Form(...),
    vehicle_unit_id: int = Form(...),
    origin_store_id: int = Form(...),
    helper_ids: str = Form("[]"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """The office/coordinator's first step in the new 7-step flow: pick a
    driver, a vehicle, and the hub they're dispatching from, and (usually)
    the helpers riding along. No shipment number or destination store yet
    -- those are only known once the driver photographs the Invoice/LM at
    Checkout. Creates the Trip in TripStatus.ASSIGNED / current_step
    "ASSIGNED"; the driver sees it on their dashboard and performs
    Checkout -> Start Trip from there."""
    if _role_value(current_user.role) not in TRIP_MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized to dispatch trips.")

    try:
        helper_ids = json.loads(helper_ids)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid helper format.")

    if len(helper_ids) != len(set(helper_ids)):
        raise HTTPException(status_code=400, detail="Duplicate helpers selected.")

    if len(helper_ids) > 3:
        raise HTTPException(status_code=400, detail="Maximum of 3 helpers allowed.")

    target_user = (
        db.query(User)
        .filter(User.id == driver_id, User.role == UserRole.DRIVER)
        .first()
    )
    if not target_user:
        raise HTTPException(status_code=400, detail="Selected driver not found.")

    existing = (
        db.query(Trip)
        .filter(
            Trip.driver_id == target_user.id,
            Trip.status.in_([TripStatus.ASSIGNED, TripStatus.ACTIVE]),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="This driver already has a trip in progress."
        )

    vehicle = (
        db.query(VehicleUnit)
        .filter(
            VehicleUnit.id == vehicle_unit_id,
            VehicleUnit.is_active.is_(True),
            VehicleUnit.is_available.is_(True),
        )
        .first()
    )
    if not vehicle:
        raise HTTPException(status_code=400, detail="Selected vehicle is unavailable.")

    origin_store = db.query(Store).filter(Store.id == origin_store_id).first()
    if not origin_store or not origin_store.is_hub:
        raise HTTPException(status_code=400, detail="Selected origin is not a valid hub.")

    driver_employee = (
        db.query(Employee).filter(Employee.id == target_user.employee_id).first()
    )
    if not driver_employee:
        raise HTTPException(status_code=400, detail="Driver employee not found.")

    required_departments = _helper_departments_for(driver_employee.department)
    helper_objects = []
    for helper_id in helper_ids:
        helper = db.query(Employee).filter(Employee.id == helper_id).first()
        if not helper:
            raise HTTPException(status_code=404, detail=f"Helper {helper_id} not found.")
        if helper.position.upper() != "HELPER":
            raise HTTPException(status_code=400, detail="Invalid helper position.")
        if helper.department not in required_departments:
            raise HTTPException(status_code=400, detail="Helper department mismatch.")
        if not helper.is_available:
            raise HTTPException(
                status_code=400, detail=f"{helper.first_name} is unavailable."
            )
        helper_objects.append(helper)

    try:
        new_trip = Trip(
            driver_id=target_user.id,
            origin_store_id=origin_store.id,
            vehicle_unit_id=vehicle.id,
            status=TripStatus.ASSIGNED,
            current_step="ASSIGNED",
        )
        db.add(new_trip)
        db.flush()

        new_trip.trip_code = _generate_trip_code(db, new_trip.start_time)

        vehicle.is_available = False

        for helper in helper_objects:
            helper.is_available = 0
            db.add(TripHelper(trip_id=new_trip.id, helper_id=helper.id))

        db.commit()
    except Exception:
        logger.exception("DISPATCH TRIP ERROR")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to dispatch trip.")

    return {
        "message": "Trip dispatched.",
        "trip_id": new_trip.id,
        "driver": target_user.username,
        "origin": origin_store.name,
        "helpers_assigned": len(helper_objects),
    }


# =========================
# CHECKOUT (driver's first step -- upload Invoice + LM, OCR-assisted)
# =========================
@router.post("/{trip_id}/checkout")
def checkout_trip(
    trip_id: int,
    shipment_no: str = Form(...),
    destination_store_id: int = Form(...),
    odometer_reading: int = Form(...),
    lat: float = Form(...),
    long: float = Form(...),
    invoice_photo: UploadFile = File(...),
    lm_photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Confirms the shipment number and destination store (pre-filled by
    the app from a prior call to /{trip_id}/checkout/ocr-preview, but
    always submitted explicitly here -- the driver has final say, an OCR
    misread never gets silently committed)."""
    trip = (
        db.query(Trip)
        .filter(
            Trip.id == trip_id,
            Trip.driver_id == current_user.id,
            Trip.status == TripStatus.ASSIGNED,
        )
        .first()
    )
    if not trip:
        raise HTTPException(status_code=404, detail="Assigned trip not found.")

    shipment_no = (shipment_no or "").strip()
    if not shipment_no:
        raise HTTPException(status_code=400, detail="Shipment number is required.")

    if odometer_reading < 0:
        raise HTTPException(status_code=400, detail="Odometer reading is required.")

    existing_ticket = (
        db.query(Trip).filter(Trip.ticket_no == shipment_no, Trip.id != trip_id).first()
    )
    if existing_ticket:
        raise HTTPException(status_code=400, detail="Shipment number already exists.")

    destination_store = db.query(Store).filter(Store.id == destination_store_id).first()
    if not destination_store:
        raise HTTPException(status_code=400, detail="Selected store not found.")
    if not destination_store.trip_rate_profile_id:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{destination_store.name}' has no trip rate profile linked. "
                "Please contact an admin to fix this store's setup."
            ),
        )
    profile = (
        db.query(TripRateProfile)
        .filter(
            TripRateProfile.id == destination_store.trip_rate_profile_id,
            TripRateProfile.is_active.is_(True),
        )
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=400,
            detail="This store's trip rate profile is invalid or inactive.",
        )

    try:
        file_service = FileService()

        invoice_url = file_service.upload_trip_checkout_invoice(
            invoice_photo, trip.id, lat=lat, long=long
        )
        db.add(
            FileModel(
                entity_type="trip",
                entity_id=trip.id,
                document_type="INVOICE_PHOTO",
                file_url=invoice_url,
                uploaded_by=current_user.id,
            )
        )

        lm_url = file_service.upload_trip_checkout_lm(
            lm_photo, trip.id, lat=lat, long=long
        )
        db.add(
            FileModel(
                entity_type="trip",
                entity_id=trip.id,
                document_type="LM_MANIFEST_PHOTO",
                file_url=lm_url,
                uploaded_by=current_user.id,
            )
        )

        trip.ticket_no = shipment_no
        trip.destination_store_id = destination_store.id
        trip.trip_rate_profile_id = profile.id
        trip.odometer_reading = odometer_reading
        trip.current_step = "CHECKOUT"

        db.commit()
    except Exception:
        logger.exception("CHECKOUT TRIP ERROR")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to checkout trip.")

    return {"message": "Checked out. Ready to start trip.", "trip_id": trip.id}


# =========================
# CHECKOUT OCR PREVIEW (non-committing -- extracts candidates for the app
# to pre-fill; the driver still confirms via POST /{trip_id}/checkout)
# =========================
@router.post("/{trip_id}/checkout/ocr-preview")
async def checkout_ocr_preview(
    trip_id: int,
    invoice_photo: UploadFile = File(...),
    lm_photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    trip = (
        db.query(Trip)
        .filter(
            Trip.id == trip_id,
            Trip.driver_id == current_user.id,
            Trip.status == TripStatus.ASSIGNED,
        )
        .first()
    )
    if not trip:
        raise HTTPException(status_code=404, detail="Assigned trip not found.")

    candidate_stores = (
        db.query(Store).filter(Store.is_hub.is_(False)).all()
    )

    invoice_bytes = await invoice_photo.read()
    lm_bytes = await lm_photo.read()
    await invoice_photo.seek(0)
    await lm_photo.seek(0)

    try:
        result = ShipmentOCRService.extract_checkout_fields(
            invoice_bytes, lm_bytes, candidate_stores
        )
    except Exception:
        logger.exception("CHECKOUT OCR PREVIEW ERROR")
        # OCR failing should never block Checkout -- fall back to empty
        # candidates so the driver can just type everything manually.
        result = {"shipment_number_candidates": [], "store_candidates": []}

    return result


# =========================
# START TRIP (button only -- begins driving)
# =========================
@router.post("/{trip_id}/start")
def start_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    trip = (
        db.query(Trip)
        .filter(
            Trip.id == trip_id,
            Trip.driver_id == current_user.id,
            Trip.status == TripStatus.ASSIGNED,
        )
        .first()
    )
    if not trip:
        raise HTTPException(status_code=404, detail="Checked-out trip not found.")

    if trip.current_step != "CHECKOUT":
        raise HTTPException(status_code=400, detail="Complete Checkout first.")

    trip.status = TripStatus.ACTIVE
    trip.current_step = "IN_TRANSIT"
    trip.start_time = datetime.utcnow()

    db.commit()

    return {"message": "Trip started.", "trip_id": trip.id}

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
        .filter(TripStop.trip_id == trip.id, TripStop.status != StopStatus.DELIVERED)
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

    if last_stop and last_stop.status == StopStatus.DELIVERED:
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
    closest_store, _ = find_nearest_store(stores, payload.lat, payload.long)

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

    trip.current_step = "ARRIVED"

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
        "stop_id": stop.id,
    }


# =========================
# START UNLOADING
# =========================
@router.post("/{trip_id}/stops/{stop_id}/start-unloading")
def start_unloading(
    trip_id: int,
    stop_id: int,
    lat: float = Form(...),
    long: float = Form(...),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
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

    stop = (
        db.query(TripStop)
        .filter(TripStop.id == stop_id, TripStop.trip_id == trip_id)
        .first()
    )
    if not stop:
        raise HTTPException(status_code=404, detail="Stop not found.")
    if stop.status != StopStatus.CHECKED_IN:
        raise HTTPException(status_code=400, detail="Must check in first.")

    stop.status = StopStatus.UNLOADING
    trip.current_step = "UNLOADING"
    db.flush()

    file_service = FileService()
    photo_url = file_service.upload_trip_unloading_photo(
        photo, trip_id, stop.id, lat=lat, long=long
    )

    db.add(
        FileModel(
            entity_type="trip_stop",
            entity_id=stop.id,
            document_type="UNLOADING_PHOTO",
            file_url=photo_url,
            uploaded_by=current_user.id,
        )
    )

    db.commit()

    return {"message": "Unloading started."}


# =========================
# CHECK-OUT
# =========================
@router.post("/{trip_id}/check-out/{stop_id}")
def check_out(
    trip_id: int,
    stop_id: int,
    lat: float = Form(...),
    long: float = Form(...),
    proof_photo: UploadFile = File(...),
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

    if stop.status != StopStatus.UNLOADING:
        raise HTTPException(status_code=400, detail="Must start unloading first")

    # if lat_out and long_out not matches the lat_in and long_in, then reject the check-out
    # ---------------------------------------
    # 3️⃣ Validate CHECKOUT GPS against STORE
    # ---------------------------------------

    store = None

    # If the stop already has a store, use it.
    if stop.store_id:
        store = (
            db.query(Store)
            .filter(Store.id == stop.store_id)
            .first()
        )

    # If check-in was an unknown location,
    # try to identify the store using the CHECKOUT GPS.
    if not store:
        stores = db.query(Store).all()

        closest_store = None
        min_distance = float("inf")

        for candidate in stores:
            # Ignore stores that don't have valid coordinates yet.
            if (
                candidate.latitude is None
                or candidate.longitude is None
                or (
                    candidate.latitude == 0
                    and candidate.longitude == 0
                )
            ):
                continue

            distance = calculate_distance_meters(
                lat,
                long,
                candidate.latitude,
                candidate.longitude,
            )

            if (
                distance <= candidate.allowed_radius_meters
                and distance < min_distance
            ):
                min_distance = distance
                closest_store = candidate

        if closest_store:
            store = closest_store
            stop.store_id = closest_store.id
            stop.requires_review = False

    # No store matched -- either the driver really is somewhere
    # unregistered, or (more likely right now) stores just don't have
    # coordinates configured yet. Neither should hard-block the driver
    # from delivering: proceed without a geofence check and flag the
    # stop for office review instead, same as check-in's unregistered-
    # location handling.
    if not store:
        stop.requires_review = True

        create_notification(
            db=db,
            type_="UNREGISTERED_STORE",
            driver_id=current_user.id,
            trip_id=trip_id,
            trip_stop_id=stop.id,
            message="Driver delivered at an unregistered/unmatched location.",
        )
    else:
        # Validate checkout GPS against the store's coordinates.
        distance = calculate_distance_meters(
            lat,
            long,
            store.latitude,
            store.longitude,
        )

        if distance > store.allowed_radius_meters:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Checkout location is too far from {store.name}. "
                    f"Allowed radius is {store.allowed_radius_meters:.0f} meters."
                ),
            )

    stop.status = StopStatus.DELIVERED
    stop.check_out_time = datetime.utcnow()
    stop.lat_out = lat
    stop.long_out = long

    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if trip:
        trip.current_step = "DELIVERED"

    db.flush()

    # Upload delivery proof photo
    file_service = FileService()

    photo_url = file_service.upload_trip_pod_photo(
        proof_photo,
        trip_id=trip_id,
        stop_id=stop.id,
        geofence_label=_geofence_label(store, distance),
        lat=lat,
        long=long,
    )

    stop_file = FileModel(
        entity_type="trip_stop",
        entity_id=stop.id,
        document_type="DELIVERY_PROOF_PHOTO",
        file_url=photo_url,
        uploaded_by=current_user.id,
    )

    db.add(stop_file)

    db.commit()

    return {"message": "Delivered successfully."}


# =========================
# BACK TO SOURCE
# =========================
@router.post("/{trip_id}/back-to-source")
def back_to_source(
    trip_id: int,
    lat: float = Form(...),
    long: float = Form(...),
    lm_perma_photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
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

    open_stop = (
        db.query(TripStop)
        .filter(TripStop.trip_id == trip.id, TripStop.status != StopStatus.DELIVERED)
        .first()
    )
    if open_stop:
        raise HTTPException(
            status_code=400, detail="You must be delivered at your current stop first."
        )

    trip.current_step = "RETURNING"
    db.flush()

    file_service = FileService()
    photo_url = file_service.upload_trip_back_to_source_photo(
        lm_perma_photo, trip_id, lat=lat, long=long
    )

    db.add(
        FileModel(
            entity_type="trip",
            entity_id=trip.id,
            document_type="BACK_TO_SOURCE_LM_PHOTO",
            file_url=photo_url,
            uploaded_by=current_user.id,
        )
    )

    db.commit()

    return {"message": "Heading back to source."}

# =========================
# TRACK TRIP LOCATION
# =========================
@router.post("/{trip_id}/track")
def track_trip_location(
    trip_id: int,
    payload: TrackLocationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),

    
):
    # ---------------------------------------
    # GPS TRAFFIC SIZE
    # ---------------------------------------

    content_length = request.headers.get("content-length")

    try:
        request_bytes = int(content_length) if content_length else None
    except (TypeError, ValueError):
        request_bytes = None

    gps_traffic_logger.info(
        "trip=%s | driver=%s | request_bytes=%s | "
        "content_type=%s | lat=%s | long=%s | accuracy=%s | speed=%s",
        trip_id,
        current_user.id,
        request_bytes if request_bytes is not None else "unknown",
        request.headers.get("content-type"),
        payload.lat,
        payload.long,
        payload.accuracy,
        payload.speed,
    )


    logger.info("=" * 100)
    logger.info("TRACK REQUEST RECEIVED")
    logger.info("Trip ID        : %s", trip_id)
    logger.info("Driver ID      : %s", current_user.id)
    logger.info("Latitude       : %s", payload.lat)
    logger.info("Longitude      : %s", payload.long)
    logger.info("Accuracy       : %s", payload.accuracy)
    logger.info("Speed          : %s", payload.speed)
    logger.info("Client Time    : %s", payload.created_at)

    try:

        logger.info("Searching ACTIVE trip...")

        trip = (
            db.query(Trip)
            .filter(
                Trip.id == trip_id,
                Trip.driver_id == current_user.id,
                Trip.status == TripStatus.ACTIVE,
            )
            .first()
        )

        logger.info("Trip Found     : %s", "YES" if trip else "NO")

        # ---------------------------------------------------------
        # Trip not found
        # ---------------------------------------------------------
        if not trip:

            logger.warning("ACTIVE trip not found.")
            logger.info("Dumping all trips of current driver...")

            driver_trips = (
                db.query(Trip)
                .filter(Trip.driver_id == current_user.id)
                .order_by(Trip.id.desc())
                .all()
            )

            logger.info("Driver Trip Count : %s", len(driver_trips))

            if len(driver_trips) == 0:
                logger.warning("Driver has NO trips.")
            else:
                for t in driver_trips:
                    logger.info(
                        "[Trip] id=%s | status=%s | start=%s | end=%s",
                        t.id,
                        t.status,
                        t.start_time,
                        t.end_time,
                    )

            logger.error("TRACK REQUEST REJECTED")
            logger.info("=" * 100)

            raise HTTPException(
                status_code=404,
                detail="Active trip not found.",
            )

        # ---------------------------------------------------------
        # Save GPS Log
        # ---------------------------------------------------------

        logger.info("Creating GPSLog object...")

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

        logger.info("Committing GPS log...")

        db.commit()

        logger.info("Commit successful.")

        logger.info("GPS Log ID     : %s", gps_log.id)
        logger.info("Trip ID        : %s", gps_log.trip_id)

        logger.info("TRACK REQUEST COMPLETED")
        logger.info("=" * 100)

        return {"message": "Tracking saved"}

    except HTTPException:
        raise

    except Exception:
        logger.exception("TRACK ENDPOINT CRASHED")

        try:
            db.rollback()
        except Exception:
            pass

        raise


# =========================
# CHECKIN (final step -- back at hub, closes the trip)
# =========================
@router.post("/{trip_id}/checkin")
def checkin_trip(
    trip_id: int,
    lat: float = Form(...),
    long: float = Form(...),
    stamped_invoice_photo: UploadFile = File(...),
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

    if trip.current_step != "RETURNING":
        raise HTTPException(status_code=400, detail="Complete Back to Source first.")

    # ---------------------------------------
    # 2️⃣ Prevent Completion If Stop Still Open
    # ---------------------------------------
    open_stop = (
        db.query(TripStop)
        .filter(TripStop.trip_id == trip.id, TripStop.status != StopStatus.DELIVERED)
        .first()
    )

    if open_stop:
        raise HTTPException(
            status_code=400,
            detail="You must be delivered at your current stop before checking in.",
        )

    # ---------------------------------------
    # 3️⃣ Validate GPS Against Allowed Hub Locations
    # ---------------------------------------
    # A trip can only be checked in once the driver's GPS is back within
    # range of a hub (Store.is_hub) -- each hub's own latitude/longitude/
    # allowed_radius_meters (from tpc_stores) defines its geofence.
    hub_stores = db.query(Store).filter(Store.is_hub.is_(True)).all()

    if not hub_stores:
        raise HTTPException(
            status_code=500, detail="Hub locations not configured in system."
        )

    valid_hub, min_distance = find_nearest_store(hub_stores, lat, long, hub_only=True)

    if not valid_hub:
        hub_names = ", ".join(store.name for store in hub_stores)
        raise HTTPException(
            status_code=400,
            detail=f"You must return to one of: {hub_names} to check in.",
        )

    # ---------------------------------------
    # 4️⃣ Complete Trip
    # ---------------------------------------

    completion_time = datetime.utcnow()

    trip.status = TripStatus.PENDING_APPROVAL
    trip.current_step = "CHECKIN"
    trip.end_time = completion_time

    completion_log = GPSLog(
        trip_id=trip.id,
        trip_stop_id=None,
        action_type=GPSActionType.TRACK,
        # action_type=GPSActionType.COMPLETED,
        actual_lat=lat,
        actual_long=long,
        created_at=completion_time,
    )

    db.add(completion_log)

    for trip_helper in trip.trip_helpers:
        trip_helper.helper.is_available = 1

    if trip.vehicle_unit:
        trip.vehicle_unit.is_available = True

    db.flush()

    # ---------------------------------------
    # 5️⃣ Upload stamped invoice photo
    #
    # TODO: same as check_out -- confirm the actual FileService method
    # name against your real service class.
    # ---------------------------------------
    file_service = FileService()

    photo_url = file_service.upload_trip_end_photo(
        stamped_invoice_photo,
        trip.id,
        geofence_label=_geofence_label(valid_hub, min_distance),
        lat=lat,
        long=long,
    )

    trip_file = FileModel(
        entity_type="trip",
        entity_id=trip.id,
        document_type="STAMPED_INVOICE_PHOTO",
        file_url=photo_url,
        uploaded_by=current_user.id,
    )

    db.add(trip_file)

    # ---------------------------------------
    # 6️⃣ Notify Admin
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

        if helper.position.upper() != "HELPER":
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
def get_my_trips(
    cutoff: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(Trip).options(
        joinedload(Trip.stops).joinedload(TripStop.store)
    ).filter(Trip.driver_id == current_user.id)

    if cutoff:
        try:
            cursor_key = parse_cutoff_value(cutoff)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cutoff format.")

        # Same period_bounds() the wallet uses, and the same field
        # (start_time) the cutoff list itself is anchored on -- keeps
        # "which trips fall in period X" consistent everywhere.
        start_utc, end_utc, _, _ = period_bounds(cursor_key)

        query = query.filter(
            Trip.start_time >= start_utc,
            Trip.start_time <= end_utc,
        )

    trips = query.order_by(Trip.start_time.desc()).all()

    results = []

    for trip in trips:
        # Delivery stores, in stop order, de-duplicated (a trip can have
        # multiple stops at the same store).
        ordered_stops = sorted(
            trip.stops, key=lambda s: s.check_in_time or datetime.min
        )
        stores = []
        for stop in ordered_stops:
            if stop.store and stop.store.name not in stores:
                stores.append(stop.store.name)

        results.append(
            {
                "id": trip.id,
                "ticket_no": trip.ticket_no,
                "trip_code": trip.trip_code,
                "vehicle": (trip.vehicle_unit.unit_code if trip.vehicle_unit else None),
                "trip_profile": (
                    trip.trip_rate_profile.profile_name
                    if trip.trip_rate_profile
                    else None
                ),
                "status": (
                    trip.status.value if hasattr(trip.status, "value") else trip.status
                ),
                "start_time": trip.start_time,
                "end_time": trip.end_time,
                "stores": stores,
            }
        )

    return api_response(results)


# =========================
# GET SINGLE TRIP (driver's own trip detail / review screen)
# =========================
# NOTE: nested under /trip-detail/ (not a bare "/{trip_id}") so this can't
# collide with any other single-segment GET route already registered on
# this router.
@router.get("/trip-detail/{trip_id}")
def get_trip_detail(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    trip = (
        db.query(Trip)
        .options(joinedload(Trip.stops).joinedload(TripStop.store))
        .filter(Trip.id == trip_id, Trip.driver_id == current_user.id)
        .first()
    )

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")

    ordered_stops = sorted(
        trip.stops, key=lambda s: s.check_in_time or datetime.min
    )
    stores = []
    for stop in ordered_stops:
        if stop.store and stop.store.name not in stores:
            stores.append(stop.store.name)

    return api_response(
        {
            "id": trip.id,
            "ticket_no": trip.ticket_no,
            "trip_code": trip.trip_code,
            "vehicle": (trip.vehicle_unit.unit_code if trip.vehicle_unit else None),
            "trip_profile": (
                trip.trip_rate_profile.profile_name
                if trip.trip_rate_profile
                else None
            ),
            "status": (
                trip.status.value if hasattr(trip.status, "value") else trip.status
            ),
            "start_time": trip.start_time,
            "end_time": trip.end_time,
            "stores": stores,
        }
    )
@router.get("/profile")
def get_driver_profile(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # 1️⃣ Get employee record
    employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
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

    # wallet
# =========================
# WALLET - SETTLEMENT DATE SOURCE
# =========================
# A trip only counts toward the driver's wallet once its
# TripFinanceReview has been fully approved. Which date within that
# review workflow determines the payroll cutoff is controlled by a
# single switch, so it can be changed later without touching the query
# logic below.
#
#   "coordinator" -> TripFinanceReview.coordinator_settlement_date
#   "office"      -> TripFinanceReview.office_reviewed_at
#   "finance"     -> TripFinanceReview.approved_at
#
# This used to be a hardcoded WALLET_SETTLEMENT_SOURCE = "coordinator"
# constant. It now lives in the tpc_app_settings table (key
# "wallet_settlement_source") so it can be changed by updating a row
# instead of editing code and redeploying -- see get_wallet_settlement_source()
# below, and app/models/app_setting.py for the table itself.
WALLET_SETTLEMENT_SOURCE_DEFAULT = "coordinator"

WALLET_SETTLEMENT_ATTR = {
    "coordinator": "coordinator_settlement_date",
    "office": "office_reviewed_at",
    "finance": "approved_at",
}


def get_wallet_settlement_source(db: Session) -> str:
    """Reads the `wallet_settlement_source` row from tpc_app_settings.

    Required by: get_wallet() and get_wallet_cutoffs() below, which both
    need to know which TripFinanceReview date column decides whether a
    trip's earnings fall inside the payroll cutoff being viewed.

    Falls back to WALLET_SETTLEMENT_SOURCE_DEFAULT if the setting row is
    missing (e.g. a fresh database before the seed migration has run) or
    holds a value outside WALLET_SETTLEMENT_ATTR, so a missing/bad setting
    degrades to the previous hardcoded behavior instead of crashing.
    """
    setting = (
        db.query(AppSetting)
        .filter(AppSetting.key == "wallet_settlement_source")
        .first()
    )

    if setting and setting.value in WALLET_SETTLEMENT_ATTR:
        return setting.value

    return WALLET_SETTLEMENT_SOURCE_DEFAULT


def _wallet_settlement_column(source: str):
    """SQLAlchemy column to filter/order by, for the given settlement source."""
    return getattr(TripFinanceReview, WALLET_SETTLEMENT_ATTR[source])


def _wallet_settlement_value(review: TripFinanceReview, source: str):
    """Actual datetime value on a loaded review, for the given settlement source."""
    return getattr(review, WALLET_SETTLEMENT_ATTR[source])


# =========================
# WALLET - AVAILABLE CUTOFFS
# =========================
@router.get("/wallet/cutoffs")
def get_wallet_cutoffs(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # NOTE: this list of selectable periods is intentionally independent
    # of finance-review approval status. It anchors on the driver's very
    # first trip so past periods stay visible/browsable for tracking
    # purposes even before they've been approved -- the *earnings shown
    # inside* a given period (see get_wallet below) are still gated on
    # an approved TripFinanceReview and its settlement date.
    settlement_source = get_wallet_settlement_source(db)

    log_wallet_event(
        "wallet_cutoffs_request",
        driver_id=current_user.id,
        settlement_source=settlement_source,
        settlement_attr=WALLET_SETTLEMENT_ATTR[settlement_source],
    )

    first_trip = (
        db.query(Trip)
        .filter(Trip.driver_id == current_user.id)
        .order_by(Trip.start_time.asc())
        .first()
    )

    current_key = period_key(now_ph())

    if not first_trip:
        _, _, value, label = period_bounds(current_key)
        log_wallet_event(
            "wallet_cutoffs_result",
            driver_id=current_user.id,
            first_trip_found=False,
            cutoffs=[{"value": value, "label": label}],
        )
        return api_response([{"value": value, "label": label}])

    cursor_key = period_key(to_ph(first_trip.start_time))  # UTC -> PH before keying

    log_wallet_event(
        "wallet_cutoffs_first_trip",
        driver_id=current_user.id,
        trip_id=first_trip.id,
        trip_start_time_raw=first_trip.start_time,
        trip_start_time_ph=to_ph(first_trip.start_time),
    )

    cutoffs = []
    for _ in range(500):
        _, _, value, label = period_bounds(cursor_key)
        cutoffs.append({"value": value, "label": label})

        if cursor_key >= current_key:
            break

        cursor_key = next_period_key(cursor_key)

    cutoffs.reverse()

    log_wallet_event(
        "wallet_cutoffs_result",
        driver_id=current_user.id,
        first_trip_found=True,
        cutoff_count=len(cutoffs),
        cutoffs=cutoffs,
    )

    return api_response(cutoffs)


@router.get("/wallet")
def get_wallet(
    cutoff: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if cutoff:
        try:
            cursor_key = parse_cutoff_value(cutoff)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cutoff format.")
    else:
        cursor_key = period_key(now_ph())

    start_utc, end_utc, cutoff_value, label = period_bounds(cursor_key)

    settlement_source = get_wallet_settlement_source(db)
    settlement_col = _wallet_settlement_column(settlement_source)

    log_wallet_event(
        "wallet_request",
        driver_id=current_user.id,
        cutoff_param=cutoff,
        settlement_source=settlement_source,
        settlement_attr=WALLET_SETTLEMENT_ATTR[settlement_source],
        cutoff_value=cutoff_value,
        cutoff_label=label,
        start_utc=start_utc,
        end_utc=end_utc,
    )

    trip_reviews = (
        db.query(Trip, TripFinanceReview)
        .join(TripFinanceReview, TripFinanceReview.trip_id == Trip.id)
        .filter(
            Trip.driver_id == current_user.id,
            TripFinanceReview.status == FinanceReviewStatus.APPROVED,
            settlement_col >= start_utc,
            settlement_col <= end_utc,
        )
        .order_by(settlement_col.asc())
        .all()
    )

    log_wallet_event(
        "wallet_matched_reviews",
        driver_id=current_user.id,
        count=len(trip_reviews),
        reviews=[
            {
                "trip_id": trip.id,
                "ticket_no": trip.ticket_no,
                "review_id": review.id,
                "review_status": review.status.value,
                "settlement_date_raw": _wallet_settlement_value(review, settlement_source),
                "settlement_date_ph": to_ph(
                    _wallet_settlement_value(review, settlement_source)
                ),
                "has_rate_profile": trip.trip_rate_profile is not None,
            }
            for trip, review in trip_reviews
        ],
    )

    trips_by_day: dict[str, list[tuple[Trip, TripFinanceReview]]] = {}
    for trip, review in trip_reviews:
        settlement_date = _wallet_settlement_value(review, settlement_source)
        day_key = to_ph(settlement_date).strftime("%Y-%m-%d")  # group by settlement date's PH day
        trips_by_day.setdefault(day_key, []).append((trip, review))

    total_earnings = 0.0
    raw_transactions = []

    for day_key, day_items in trips_by_day.items():
        for idx, (trip, review) in enumerate(day_items):
            profile = trip.trip_rate_profile
            if not profile:
                continue

            rate = float(
                profile.driver_first_trip_rate
                if idx == 0
                else profile.driver_next_trip_rate
            )
            total_earnings += rate

            raw_transactions.append({
                "id": str(trip.id),
                "shipment": f"Shipment #{trip.ticket_no}",
                "trip_label": f"Trip #{idx + 1}",
                "start_time": trip.start_time,
                "end_time": trip.end_time,
                "sort_time": _wallet_settlement_value(review, settlement_source),
                "amount": rate,
                "cutoff": cutoff_value,
            })

    raw_transactions.sort(key=lambda t: t["sort_time"], reverse=True)

    transactions = [
        {
            "id": t["id"],
            "shipment": t["shipment"],
            "trip": t["trip_label"],
            "start_time": to_ph(t["start_time"]).strftime("%b %d • %I:%M %p"),
            "end_time": to_ph(t["end_time"]).strftime("%b %d • %I:%M %p"),
            "amount": t["amount"],
            "cutoff": t["cutoff"],
        }
        for t in raw_transactions
    ]

    # =========================
    # EXPECTED PAYMENT
    # =========================
    # `earnings` above only counts trips whose finance review has been
    # fully APPROVED and settled within this cutoff -- so a driver who
    # completed trips in this period sees ₱0 until office/finance review
    # catches up. `expected_earnings` is a separate, independent estimate:
    # every trip that *started* in this cutoff, rated the same way
    # (first-trip-of-day vs next-trip-of-day), regardless of review
    # status. It intentionally is not reconciled against `earnings` --
    # the two use different day-groupings (settlement day vs trip day) --
    # it's purely "what this driver can expect for trips in this period".
    expected_trips_qs = (
        db.query(Trip)
        .filter(
            Trip.driver_id == current_user.id,
            Trip.start_time >= start_utc,
            Trip.start_time <= end_utc,
        )
        .order_by(Trip.start_time.asc())
        .all()
    )

    expected_by_day: dict[str, list[Trip]] = {}
    for trip in expected_trips_qs:
        day_key = to_ph(trip.start_time).strftime("%Y-%m-%d")
        expected_by_day.setdefault(day_key, []).append(trip)

    expected_earnings = 0.0
    for day_items in expected_by_day.values():
        for idx, trip in enumerate(day_items):
            profile = trip.trip_rate_profile
            if not profile:
                continue

            rate = float(
                profile.driver_first_trip_rate
                if idx == 0
                else profile.driver_next_trip_rate
            )
            expected_earnings += rate

    log_wallet_event(
        "wallet_response",
        driver_id=current_user.id,
        cutoff_value=cutoff_value,
        cutoff_label=label,
        earnings=round(total_earnings, 2),
        trips=len(trip_reviews),
        expected_earnings=round(expected_earnings, 2),
        expected_trips=len(expected_trips_qs),
        transactions=transactions,
    )

    return api_response({
        "cutoff_value": cutoff_value,
        "cutoff_label": label,
        "earnings": round(total_earnings, 2),
        "trips": len(trip_reviews),
        "expected_earnings": round(expected_earnings, 2),
        "expected_trips": len(expected_trips_qs),
        "transactions": transactions,
    })