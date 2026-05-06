# app/api/admin/trips.py

from app.models.gps_log import GPSLog
from app.models.trip_models import GPSActionType
from app.schemas import trip
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, date, timedelta

from app.core.database import get_db
from app.core.dependencies import get_current_admin, get_current_user
from app.models.trips import Trip, TripStatus
from app.models.notification import Notification
from app.models.trip_stops import TripStop
from app.models.user import User
from app.models.employees import Employee
from app.models.trip_helper import TripHelper
from app.models.files import File

router = APIRouter(prefix="/admin/trips", tags=["Admin Trips"])


def to_ph_time(dt):
    if not dt:
        return None
    return dt + timedelta(hours=8)


# =========================
# SUMMARY
# =========================
@router.get("/summary")
def get_trip_summary(
    db: Session = Depends(get_db), current_admin=Depends(get_current_admin)
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
    db: Session = Depends(get_db), current_admin=Depends(get_current_admin)
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
            "start_time": (trip.start_time + timedelta(hours=8)).strftime(
                "%Y-%m-%d %I:%M:%S %p"
            ),
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
    db: Session = Depends(get_db), current_admin=Depends(get_current_admin)
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
            "status": trip.status.value,
            "start_time": (trip.start_time + timedelta(hours=8)).strftime(
                "%Y-%m-%d %I:%M:%S %p"
            ),
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
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    trip = db.query(Trip).filter(Trip.id == trip_id).first()

    if not trip:
        raise HTTPException(404, "Trip not found")

    if trip.status != TripStatus.PENDING_APPROVAL:
        raise HTTPException(400, "Trip not pending approval")

    trip.status = TripStatus.COMPLETED
    trip.end_time = trip.end_time or datetime.utcnow()

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
        notification.reviewed_at = datetime.utcnow()

    db.commit()

    return {"message": "Trip approved successfully"}


@router.get("/{trip_id}/review")
def review_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    trip = (
        db.query(Trip)
        .options(
            joinedload(Trip.driver).joinedload(User.employee),
            joinedload(Trip.origin_store),
            joinedload(Trip.stops).joinedload(TripStop.store),
        )
        .filter(Trip.id == trip_id)
        .first()
    )

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")

    trip_helpers = (
        db.query(Employee)
        .join(TripHelper, TripHelper.helper_id == Employee.id)
        .filter(TripHelper.trip_id == trip_id)
        .all()
    )
    start_photo = (
        db.query(File)
        .filter(
            File.entity_type == "trip",
            File.entity_id == trip_id,
            File.document_type == "START_TRIP_PHOTO",
        )
        .first()
    )

    helpers_data = [
        {
            "id": helper.id,
            "first_name": helper.first_name,
            "last_name": helper.last_name,
        }
        for helper in trip_helpers
    ]

    # GPS LOGS
    gps_logs = (
        db.query(GPSLog)
        .filter(GPSLog.trip_id == trip_id)
        .order_by(GPSLog.created_at.asc())
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
            "actual_lat": float(log.actual_lat) if log.actual_lat is not None else None,
            "actual_long": (
                float(log.actual_long) if log.actual_long is not None else None
            ),
            "accuracy": log.accuracy,
            "speed": log.speed,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in gps_logs
    ]

    # Convert UTC -> PH time
    def to_ph(dt):
        if not dt:
            return None
        return (dt + timedelta(hours=8)).strftime("%b %d, %Y, %I:%M %p")

    # SORT STOPS BY CHECK-IN TIME (important for route drawing)
    sorted_stops = sorted(trip.stops, key=lambda x: x.check_in_time or datetime.min)

    stops_data = []

    for stop in sorted_stops:
        stops_data.append(
            {
                "store_name": stop.store.name if stop.store else "Unknown",
                "check_in_time": to_ph(stop.check_in_time),
                "check_out_time": to_ph(stop.check_out_time),
                # actual recorded gps
                "lat_in": stop.lat_in,
                "long_in": stop.long_in,
                "lat_out": stop.lat_out,
                "long_out": stop.long_out,
                # official store coordinates
                "store_lat": stop.store.latitude if stop.store else None,
                "store_long": stop.store.longitude if stop.store else None,
                "allowed_radius": (
                    stop.store.allowed_radius_meters if stop.store else None
                ),
            }
        )

    return {
        "trip_id": trip.id,
        "ticket_no": trip.ticket_no,
        "status": trip.status.value,
        "driver_first_name": (
            trip.driver.employee.first_name if trip.driver.employee else "-"
        ),
        "driver_last_name": (
            trip.driver.employee.last_name if trip.driver.employee else "-"
        ),
        "start_photo": start_photo.file_url if start_photo else None,
        # helpers
        "helpers": helpers_data,
        # origin info
        "origin_store": trip.origin_store.name if trip.origin_store else "-",
        "origin_lat": trip.origin_store.latitude if trip.origin_store else None,
        "origin_long": trip.origin_store.longitude if trip.origin_store else None,
        "start_time": to_ph(trip.start_time),
        "end_time": to_ph(trip.end_time),
        "stops": stops_data,
        "gps_logs": gps_logs_data,
    }


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
