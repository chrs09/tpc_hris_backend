# app/api/admin/trips.py

from app.models.gps_log import GPSLog
from app.models.trip_models import GPSActionType
from app.schemas import trip
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, date, timedelta

from app.core.database import get_db
from app.core.dependencies import get_current_trip_manager, get_current_user
from app.models.trips import Trip, TripStatus
from app.models.notification import Notification
from app.models.trip_stops import TripStop
from app.models.user import User
from app.models.employees import Employee
from app.models.trip_helper import TripHelper
from app.models.trip_finance_review import FinanceReviewStatus, TripFinanceReview
from app.models.files import File
from app.utils.timezone import utc_to_ph

router = APIRouter(prefix="/admin/trips", tags=["Admin Trips"])


# =========================
# SUMMARY
# =========================
@router.get("/summary")
def get_trip_summary(
    db: Session = Depends(get_db), current_admin=Depends(get_current_trip_manager)
):
    today = date.today()

    return {
        "pending_trips": db.query(Trip)
        .filter(Trip.status == TripStatus.PENDING_APPROVAL)
        .count(),
        "active_trips": db.query(Trip).filter(Trip.status == TripStatus.ACTIVE).count(),
        "completed_today": db.query(Trip)
        .filter(Trip.status == TripStatus.COMPLETED, Trip.end_time >= today)
        .count(),
    }


# =========================
# GET PENDING
# =========================
@router.get("/pending")
def get_pending_trips(
    db: Session = Depends(get_db), current_admin=Depends(get_current_trip_manager)
):
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.driver))
        .filter(Trip.status == TripStatus.PENDING_APPROVAL)
        .order_by(Trip.start_time.desc())
        .all()
    )

    return [
        {
            "id": trip.id,
            "ticket_no": trip.ticket_no,
            "status": trip.status.value,
            "start_time": utc_to_ph(trip.start_time).strftime("%Y-%m-%d %I:%M:%S %p"),
            "stops_count": db.query(TripStop)
            .filter(TripStop.trip_id == trip.id)
            .count(),
            "username": trip.driver.username,
        }
        for trip in trips
    ]


# =========================
# GET ACTIVE
# =========================
@router.get("/active")
def get_active_trips(
    db: Session = Depends(get_db), current_admin=Depends(get_current_trip_manager)
):
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.driver))
        .filter(Trip.status == TripStatus.ACTIVE)
        .order_by(Trip.start_time.desc())
        .all()
    )

    return [
        {
            "id": trip.id,
            "ticket_no": trip.ticket_no,
            "vehicle_unit": (trip.vehicle_unit.unit_code if trip.vehicle_unit else "-"),
            "trip_profile": (
                trip.trip_rate_profile.profile_name if trip.trip_rate_profile else "-"
            ),
            "status": trip.status.value,
            "start_time": utc_to_ph(trip.start_time).strftime("%Y-%m-%d %I:%M:%S %p"),
            "username": trip.driver.username,  # 👈 THIS IS ALL YOU NEED
        }
        for trip in trips
    ]


# =========================
# APPROVE TRIP
# =========================

@router.post("/{trip_id}/approve")
def approve_trip(
    trip_id: int,
    remarks: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_trip_manager),
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
    # 4. PREVENT DUPLICATE REVIEW RECORD
    # =========================================================

    existing_review = (
        db.query(TripFinanceReview)
        .filter(
            TripFinanceReview.trip_id == trip.id
        )
        .first()
    )

    if existing_review:
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
    # 7. CREATE REVIEW RECORD
    # =========================================================

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

    return {
        "message": (
            "Trip approved by coordinator "
            "and sent for office review"
        ),
        "trip_id": trip.id,
        "trip_status": trip.status.value,
        "review_status": review.status.value,
        "coordinator_settlement_date": (
            review.coordinator_settlement_date
        ),
    }

@router.post("/{trip_id}/reject")
def reject_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_trip_manager),
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
    current_admin=Depends(get_current_trip_manager),
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
    # 3. GET START TRIP PHOTO
    #
    # Expected:
    # entity_type   = trip
    # entity_id     = trip_id
    # document_type = START_TRIP_PHOTO
    #
    # Example path:
    # /uploads/trips/49/start/xxx.jpg
    # =========================================================
    start_photo = (
        db.query(File)
        .filter(
            File.entity_type == "trip",
            File.entity_id == trip_id,
            File.document_type == "START_TRIP_PHOTO",
        )
        .order_by(File.id.desc())
        .first()
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
    # 10. CREATE POD LOOKUP
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
            delivery_proof_by_stop_id[
                photo.entity_id
            ] = photo.file_url

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
                "store_name": (
                    stop.store.name
                    if stop.store
                    else "Unknown"
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

                # POD / Delivery Proof
                "delivery_proof_photo": (
                    delivery_proof_by_stop_id.get(
                        stop.id
                    )
                ),
            }
        )

    # =========================================================
    # 12. RETURN COMPLETE TRIP REVIEW DATA
    # =========================================================
    return {
        # -------------------------
        # TRIP
        # -------------------------
        "trip_id": trip.id,
        "ticket_no": trip.ticket_no,
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
        "start_photo": (
            start_photo.file_url
            if start_photo
            else None
        ),

        "stamped_invoice_photo": (
            stamped_invoice_photo.file_url
            if stamped_invoice_photo
            else None
        ),

        # -------------------------
        # STOPS + POD
        # -------------------------
        "stops": stops_data,

        # -------------------------
        # GPS ROUTE
        # -------------------------
        "gps_logs": gps_logs_data,
    }

@router.get("/completed")
def get_completed_trips(
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_trip_manager),
):
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.driver))
        .filter(Trip.status == TripStatus.COMPLETED)
        .order_by(Trip.end_time.desc())
        .all()
    )

    return [
        {
            "id": trip.id,
            "ticket_no": trip.ticket_no,
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
        }
        for trip in trips
    ]


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

    return {"message": "Location tracked"}