# app/api/office/trips.py

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.models.employees import Employee
from app.models.files import File
from app.models.gps_log import GPSLog
from app.models.trip_finance_review import (
    FinanceReviewStatus,
    TripFinanceReview,
)
from app.models.trip_helper import TripHelper
from app.models.trip_stops import TripStop
from app.models.trips import Trip, TripStatus
from app.models.user import User

from app.utils.timezone import utc_to_ph


router = APIRouter(
    prefix="/office/trips",
    tags=["Office Trip Review"],
)


# =========================================================
# HELPER: UTC -> PHILIPPINE TIME
# =========================================================
def to_ph(dt):
    if not dt:
        return None

    return utc_to_ph(dt).strftime(
        "%b %d, %Y, %I:%M %p"
    )


# =========================================================
# GET PENDING OFFICE REVIEW TRIPS
#
# NOTE:
# Your current coordinator/admin approval endpoint sets:
#
# Trip.status = PENDING_FINANCE_REVIEW
# TripFinanceReview.status = FOR_REVIEW
#
# Therefore, this endpoint uses the TripFinanceReview record
# to determine which trips are waiting for review.
# =========================================================
# =========================================================
# GET PENDING OFFICE REVIEW TRIPS
# =========================================================
# =========================================================
# GET PENDING OFFICE REVIEW TRIPS
# =========================================================
@router.get("/pending")
def get_pending_office_review_trips(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    reviews = (
        db.query(TripFinanceReview)
        .options(
            joinedload(TripFinanceReview.trip)
            .joinedload(Trip.driver)
        )
        .join(
            Trip,
            Trip.id == TripFinanceReview.trip_id,
        )
        .filter(
            Trip.status == TripStatus.PENDING_OFFICE_REVIEW,
            TripFinanceReview.status == FinanceReviewStatus.OFFICE_REVIEW,
        )
        .order_by(
            TripFinanceReview.coordinator_settlement_date.desc()
        )
        .all()
    )

    result = []

    for review in reviews:
        trip = review.trip

        if not trip:
            continue

        stops_count = (
            db.query(TripStop)
            .filter(
                TripStop.trip_id == trip.id
            )
            .count()
        )

        result.append(
            {
                "id": trip.id,
                "trip_id": trip.id,
                "ticket_no": trip.ticket_no,

                "status": (
                    trip.status.value
                    if hasattr(trip.status, "value")
                    else trip.status
                ),

                "review_status": (
                    review.status.value
                    if hasattr(review.status, "value")
                    else review.status
                ),

                "username": (
                    trip.driver.username
                    if trip.driver
                    else "-"
                ),

                "start_time": (
                    utc_to_ph(trip.start_time).strftime(
                        "%Y-%m-%d %I:%M:%S %p"
                    )
                    if trip.start_time
                    else None
                ),

                "end_time": (
                    utc_to_ph(trip.end_time).strftime(
                        "%Y-%m-%d %I:%M:%S %p"
                    )
                    if trip.end_time
                    else None
                ),

                "stops_count": stops_count,

                "coordinator_remarks": review.coordinator_remarks,

                "coordinator_settlement_date": (
                    utc_to_ph(
                        review.coordinator_settlement_date
                    ).strftime("%b %d, %Y %I:%M %p")
                    if review.coordinator_settlement_date
                    else None
                ),

                "submitted_at": (
                    utc_to_ph(review.submitted_at).strftime(
                        "%b %d, %Y %I:%M %p"
                    )
                    if review.submitted_at
                    else None
                ),
            }
        )

    return result

# =========================================================
# REVIEW A SINGLE TRIP
#
# Returns:
# - Trip
# - Driver
# - Helpers
# - Vehicle
# - Rate profile
# - Origin
# - Start/end times
# - Coordinator remarks
# - Start photo
# - Stamped invoice photo
# - Stops
# - POD per stop
# - GPS logs
# =========================================================
@router.get("/{trip_id}/review")
def review_office_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # =====================================================
    # 1. GET TRIP + RELATED DATA
    # =====================================================
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

    if trip.status != TripStatus.PENDING_OFFICE_REVIEW:
        raise HTTPException(
            status_code=400,
            detail="Trip is not pending office review.",
        )

    # =====================================================
    # 2. GET + VALIDATE FINANCE/OFFICE REVIEW RECORD
    # Must happen before using finance_review.status.
    # =====================================================
    finance_review = (
        db.query(TripFinanceReview)
        .filter(TripFinanceReview.trip_id == trip_id)
        .order_by(TripFinanceReview.id.desc())
        .first()
    )

    if not finance_review:
        raise HTTPException(
            status_code=404,
            detail="Trip review record not found.",
        )

    if finance_review.status != FinanceReviewStatus.OFFICE_REVIEW:
        raise HTTPException(
            status_code=400,
            detail="Trip is not awaiting office review.",
        )

    # =====================================================
    # 3. GET TRIP HELPERS
    # =====================================================
    trip_helpers = (
        db.query(Employee)
        .join(
            TripHelper,
            TripHelper.helper_id == Employee.id,
        )
        .filter(TripHelper.trip_id == trip_id)
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

    # =====================================================
    # 4. GET START TRIP PHOTO
    # =====================================================
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

    # =====================================================
    # 5. GET STAMPED INVOICE / END TRIP PHOTO
    # =====================================================
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

    # =====================================================
    # 6. GET GPS LOGS
    # =====================================================
    gps_logs = (
        db.query(GPSLog)
        .filter(GPSLog.trip_id == trip_id)
        .order_by(GPSLog.created_at.asc())
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

    # =====================================================
    # 7. SORT STOPS
    # =====================================================
    sorted_stops = sorted(
        trip.stops,
        key=lambda stop: stop.check_in_time or datetime.min,
    )

    # =====================================================
    # 8. GET STOP IDS
    # =====================================================
    stop_ids = [stop.id for stop in sorted_stops]

    # =====================================================
    # 9. GET DELIVERY PROOF PHOTOS
    # =====================================================
    delivery_proof_photos = []

    if stop_ids:
        delivery_proof_photos = (
            db.query(File)
            .filter(
                File.entity_type == "trip_stop",
                File.entity_id.in_(stop_ids),
                File.document_type == "DELIVERY_PROOF_PHOTO",
            )
            .order_by(File.id.desc())
            .all()
        )

    # =====================================================
    # 10. CREATE POD LOOKUP
    # Only the newest POD for each stop is returned.
    # =====================================================
    delivery_proof_by_stop_id = {}

    for photo in delivery_proof_photos:
        if photo.entity_id not in delivery_proof_by_stop_id:
            delivery_proof_by_stop_id[photo.entity_id] = photo.file_url

    # =====================================================
    # 11. BUILD STOPS DATA
    # =====================================================
    stops_data = []

    for stop in sorted_stops:
        stops_data.append(
            {
                "id": stop.id,
                "store_name": (
                    stop.store.name
                    if stop.store
                    else "Unknown"
                ),
                "check_in_time": to_ph(stop.check_in_time),
                "check_out_time": to_ph(stop.check_out_time),
                "lat_in": stop.lat_in,
                "long_in": stop.long_in,
                "lat_out": stop.lat_out,
                "long_out": stop.long_out,
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
                "allowed_radius": (
                    stop.store.allowed_radius_meters
                    if stop.store
                    else None
                ),
                "delivery_proof_photo": (
                    delivery_proof_by_stop_id.get(stop.id)
                ),
            }
        )

    # =====================================================
    # 12. RETURN COMPLETE REVIEW DATA
    # =====================================================
    return {
        "review_id": finance_review.id,
        "review_status": (
            finance_review.status.value
            if hasattr(finance_review.status, "value")
            else finance_review.status
        ),
        "coordinator_id": finance_review.coordinator_id,
        "coordinator_remarks": finance_review.coordinator_remarks,
        "coordinator_settlement_date": to_ph(
            finance_review.coordinator_settlement_date
        ),
        "submitted_at": to_ph(finance_review.submitted_at),
        "office_reviewer_id": finance_review.office_reviewer_id,
        "office_remarks": finance_review.office_remarks,
        "office_reviewed_at": to_ph(
            finance_review.office_reviewed_at
        ),

        "trip_id": trip.id,
        "ticket_no": trip.ticket_no,
        "status": (
            trip.status.value
            if hasattr(trip.status, "value")
            else trip.status
        ),

        "vehicle": (
            {
                "id": trip.vehicle_unit.id,
                "unit_code": trip.vehicle_unit.unit_code,
                "plate_number": trip.vehicle_unit.plate_number,
            }
            if trip.vehicle_unit
            else None
        ),

        "trip_rate_profile": (
            {
                "id": trip.trip_rate_profile.id,
                "profile_name": trip.trip_rate_profile.profile_name,
                "helper_count": trip.trip_rate_profile.helper_count,
            }
            if trip.trip_rate_profile
            else None
        ),

        "driver_first_name": (
            trip.driver.employee.first_name
            if trip.driver and trip.driver.employee
            else "-"
        ),
        "driver_last_name": (
            trip.driver.employee.last_name
            if trip.driver and trip.driver.employee
            else "-"
        ),

        "helpers": helpers_data,

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

        "start_time": to_ph(trip.start_time),
        "end_time": to_ph(trip.end_time),

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

        "stops": stops_data,
        "gps_logs": gps_logs_data,
    }

# =========================================================
# FORWARD / APPROVE OFFICE REVIEW
#
# IMPORTANT:
# This endpoint assumes your TripFinanceReview model has:
#
# office_reviewer_id
# office_remarks
# office_reviewed_at
#
# If those columns do not exist yet, they must be added
# before using this endpoint.
# =========================================================
@router.post("/{trip_id}/forward-to-finance")
def forward_trip_to_finance(
    trip_id: int,
    remarks: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # =====================================================
    # VALIDATE REMARKS
    # =====================================================
    if not remarks or not remarks.strip():
        raise HTTPException(
            status_code=400,
            detail="Office remarks are required.",
        )

    # =====================================================
    # GET TRIP
    # =====================================================
    trip = (
        db.query(Trip)
        .filter(
            Trip.id == trip_id
        )
        .first()
    )

    if not trip:
        raise HTTPException(
            status_code=404,
            detail="Trip not found.",
        )

    if trip.status != TripStatus.PENDING_OFFICE_REVIEW:
        raise HTTPException(
            status_code=400,
            detail="Trip is not pending office review.",
        )

    # =====================================================
    # GET REVIEW RECORD
    # =====================================================
    finance_review = (
        db.query(TripFinanceReview)
        .filter(
            TripFinanceReview.trip_id == trip_id
        )
        .first()
    )

    if not finance_review:
        raise HTTPException(
            status_code=404,
            detail="Finance review record not found.",
        )

    if finance_review.status != FinanceReviewStatus.OFFICE_REVIEW:
        raise HTTPException(
            status_code=400,
            detail="Trip has already been processed.",
        )

    # =====================================================
    # SAVE OFFICE REVIEW
    # =====================================================
    finance_review.office_reviewer_id = current_user.id

    finance_review.office_remarks = remarks.strip()

    finance_review.office_reviewed_at = datetime.utcnow()

    finance_review.status = FinanceReviewStatus.FINANCE_REVIEW

    # =====================================================
    # MOVE TRIP TO FINANCE
    # =====================================================
    trip.status = TripStatus.PENDING_FINANCE_REVIEW

    db.commit()

    db.refresh(finance_review)

    return {
        "message": "Trip forwarded to Finance successfully.",
        "trip_id": trip.id,
        "review_id": finance_review.id,
        "review_status": finance_review.status.value,
        "trip_status": trip.status.value,
        "office_reviewed_at": to_ph(
            finance_review.office_reviewed_at
        ),
    }

