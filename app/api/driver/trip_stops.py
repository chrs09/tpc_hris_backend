"""
Driver trip stop endpoints.
Handles GPS check-in and check-out logic with validation and notifications.
"""

# =============================
# Standard Library
# =============================
from datetime import datetime

# =============================
# Third-Party
# =============================
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

# =============================
# Local Imports
# =============================
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.trip_stops import TripStop, StopStatus
from app.models.gps_log import GPSLog, GPSActionType
from app.models.trips import Trip, TripStatus
from app.services.gps_service import calculate_distance_meters
from app.services.notification_service import create_notification

router = APIRouter(
    prefix="/driver/trip-stops",
    tags=["Driver Trip Stops"],
)


# =============================
# Request Schema
# =============================
class GPSActionRequest(BaseModel):
    action_type: GPSActionType
    actual_lat: float
    actual_long: float


# =============================
# Helper: Enforce Stop Order
# =============================
# def validate_stop_sequence(db: Session, trip_stop: TripStop) -> None:
#     """
#     Ensures driver cannot jump to next stop
#     without completing the previous one.
#     """
#     previous_stop = (
#         db.query(TripStop)
#         .filter(
#             TripStop.trip_id == trip_stop.trip_id,
#             TripStop.stop_order == trip_stop.stop_order - 1,
#         )
#         .first()
#     )

#     if previous_stop and previous_stop.status != StopStatus.CHECKED_OUT:
#         raise HTTPException(
#             status_code=400,
#             detail="Previous stop must be checked out first.",
#         )


# =============================
# GPS Action Endpoint
# =============================
@router.post("/{trip_stop_id}/gps-action")
def gps_action(
    trip_stop_id: int,
    payload: GPSActionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Handles driver check-in and check-out.
    Validates GPS distance and updates stop status.
    """

    trip_stop = db.query(TripStop).filter(TripStop.id == trip_stop_id).first()

    if not trip_stop:
        raise HTTPException(status_code=404, detail="Trip stop not found.")

    trip = trip_stop.trip

    if trip.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your trip.")

    if trip.status != TripStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Trip is not active.")

    # Enforce stop order
    # validate_stop_sequence(db, trip_stop)

    store = trip_stop.store

    # Calculate GPS distance
    distance = calculate_distance_meters(
        payload.actual_lat,
        payload.actual_long,
        store.latitude,
        store.longitude,
    )

    is_valid = distance <= store.allowed_radius_meters

    # Always log GPS attempt
    gps_log = GPSLog(
        trip_stop_id=trip_stop.id,
        action_type=payload.action_type,
        actual_lat=payload.actual_lat,
        actual_long=payload.actual_long,
        store_lat=store.latitude,
        store_long=store.longitude,
        calculated_distance=distance,
        is_valid=is_valid,
        created_at=datetime.utcnow(),
    )

    db.add(gps_log)

    now = datetime.utcnow()

    # -----------------------------
    # CHECK IN
    # -----------------------------
    if payload.action_type == GPSActionType.CHECK_IN:

        if trip_stop.status != StopStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail="Stop already checked in or completed.",
            )

        trip_stop.check_in_time = now
        trip_stop.lat_in = payload.actual_lat
        trip_stop.long_in = payload.actual_long
        trip_stop.gps_valid_in = is_valid
        trip_stop.status = StopStatus.CHECKED_IN

    # -----------------------------
    # CHECK OUT
    # -----------------------------
    elif payload.action_type == GPSActionType.CHECK_OUT:

        if trip_stop.status != StopStatus.CHECKED_IN:
            raise HTTPException(
                status_code=400,
                detail="You must check-in first.",
            )

        trip_stop.check_out_time = now
        trip_stop.lat_out = payload.actual_lat
        trip_stop.long_out = payload.actual_long
        trip_stop.gps_valid_out = is_valid
        trip_stop.status = StopStatus.CHECKED_OUT

    else:
        raise HTTPException(status_code=400, detail="Invalid action type.")

    # -----------------------------
    # If GPS Invalid → Require Review
    # -----------------------------
    if not is_valid:
        trip_stop.requires_review = True

        create_notification(
            db=db,
            type_="GPS_OUT_OF_RANGE",
            driver_id=current_user.id,
            trip_id=trip.id,
            trip_stop_id=trip_stop.id,
            message="Driver checked outside allowed radius.",
        )

    db.commit()

    return {
        "message": "GPS action recorded successfully.",
        "distance_meters": round(distance, 2),
        "gps_valid": is_valid,
        "stop_status": trip_stop.status,
    }


@router.post("/{trip_id}/complete")
def complete_trip(
    trip_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)
):

    trip = db.query(Trip).filter(Trip.id == trip_id).first()

    if not trip or trip.driver_id != current_user.id:
        raise HTTPException(status_code=404, detail="Trip not found")

    if any(stop.status != StopStatus.CHECKED_OUT for stop in trip.stops):
        raise HTTPException(status_code=400, detail="All stops must be checked out")

    trip.end_time = datetime.utcnow()
    trip.status = TripStatus.COMPLETED

    create_notification(
        db=db,
        type_="TRIP_COMPLETED",
        driver_id=current_user.id,
        trip_id=trip.id,
        message="Trip completed. Awaiting admin confirmation.",
    )

    db.commit()

    return {"message": "Trip completed successfully"}
