# app/api/finance/trips.py

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.models.trips import Trip, TripStatus
from app.models.trip_finance_review import TripFinanceReview, FinanceReviewStatus
from app.models.trip_stops import TripStop
from app.models.trip_helper import TripHelper
from app.models.employees import Employee
from app.models.gps_log import GPSLog
from app.models.files import File
from app.utils.timezone import utc_to_ph

router = APIRouter(prefix="/finance/trips", tags=["Finance Trips"])


def to_ph(dt):
    if not dt:
        return None
    return utc_to_ph(dt).strftime("%b %d, %Y, %I:%M %p")


def coordinator_name(review):
    if review.coordinator.employee:
        return f"{review.coordinator.employee.first_name} {review.coordinator.employee.last_name}"
    return review.coordinator.username


# =========================
# SUMMARY
# =========================
@router.get("/summary")
def get_finance_trip_summary(
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    finance_review = (
        db.query(TripFinanceReview)
        .filter(
            TripFinanceReview.status
            == FinanceReviewStatus.FINANCE_REVIEW
        )
        .count()
    )

    approved = (
        db.query(TripFinanceReview)
        .filter(
            TripFinanceReview.status
            == FinanceReviewStatus.APPROVED
        )
        .count()
    )

    return {
        "finance_review_count": finance_review,
        "approved_count": approved,
        "total_count": finance_review + approved,
        "synced_to_payroll_count": approved,
    }
# =========================
# LIST (?status=finance_review | approved)
# =========================
@router.get("")
def get_finance_trips(
    status: str = "finance_review",
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    try:
        review_status = FinanceReviewStatus(status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid status. "
                "Use 'finance_review' or 'approved'."
            ),
        )

    reviews = (
        db.query(TripFinanceReview)
        .options(
            joinedload(TripFinanceReview.trip)
            .joinedload(Trip.driver),

            joinedload(TripFinanceReview.coordinator),
        )
        .filter(
            TripFinanceReview.status == review_status
        )
        .order_by(
            TripFinanceReview.submitted_at.desc()
        )
        .all()
    )

    return [
        {
            "id": review.trip.id,
            "trip_id": review.trip.id,
            "shipment_number": review.trip.ticket_no,
            "ticket_no": review.trip.ticket_no,

            # FinanceReviewCard uses this field.
            "status": review.status.value,

            # Kept separately for the workflow state.
            "trip_status": (
                review.trip.status.value
                if hasattr(review.trip.status, "value")
                else review.trip.status
            ),

            "driver_first_name": (
                review.trip.driver.employee.first_name
                if review.trip.driver
                and review.trip.driver.employee
                else "-"
            ),
            "driver_last_name": (
                review.trip.driver.employee.last_name
                if review.trip.driver
                and review.trip.driver.employee
                else "-"
            ),
            "start_time": to_ph(review.trip.start_time),
            "end_time": to_ph(review.trip.end_time),
            "stops_count": (
                db.query(TripStop)
                .filter(TripStop.trip_id == review.trip.id)
                .count()
            ),
            "coordinator_name": coordinator_name(review),
            "coordinator_remarks": review.coordinator_remarks,
            "submitted_at": to_ph(review.submitted_at),
            "office_reviewer_id": review.office_reviewer_id,
            "office_remarks": review.office_remarks,
            "office_reviewed_at": to_ph(
                review.office_reviewed_at
            ),
            "approved_at": (
                to_ph(review.approved_at)
                if review.approved_at
                else None
            ),
        }
        for review in reviews
    ]


# =========================
# DETAIL
# =========================
@router.get("/{trip_id}")
def get_finance_trip_detail(
    trip_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    review = (
        db.query(TripFinanceReview)
        .options(
            joinedload(TripFinanceReview.trip).joinedload(Trip.driver),
            joinedload(TripFinanceReview.trip).joinedload(Trip.origin_store),
            joinedload(TripFinanceReview.trip)
            .joinedload(Trip.stops)
            .joinedload(TripStop.store),
            joinedload(TripFinanceReview.coordinator),
        )
        .filter(TripFinanceReview.trip_id == trip_id)
        .first()
    )

    if not review:
        raise HTTPException(404, "Trip not submitted for finance review.")

    trip = review.trip

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
        .order_by(File.id.desc())
        .first()
    )

    # END TRIP / STAMPED INVOICE PHOTO
    end_photo = (
        db.query(File)
        .filter(
            File.entity_type == "trip",
            File.entity_id == trip_id,
            File.document_type == "STAMPED_INVOICE_PHOTO",
        )
        .order_by(File.id.desc())
        .first()
    )

    # GPS LOGS — same as admin/trips.py review_trip, needed to draw the route
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
            "actual_lat": float(log.actual_lat) if log.actual_lat is not None else None,
            "actual_long": (
                float(log.actual_long) if log.actual_long is not None else None
            ),
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in gps_logs
    ]

    sorted_stops = sorted(trip.stops, key=lambda x: x.check_in_time or datetime.min)

    # =========================
    # DELIVERY PROOF / POD PHOTOS
    # =========================

    stop_ids = [stop.id for stop in sorted_stops]

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

    # Map each TripStop ID to its newest POD photo
    delivery_proof_by_stop_id = {}

    for photo in delivery_proof_photos:
        if photo.entity_id not in delivery_proof_by_stop_id:
            delivery_proof_by_stop_id[photo.entity_id] = photo.file_url

    return {
        "id": trip.id,
        "trip_id": trip.id,
        "shipment_number": trip.ticket_no,
        "ticket_no": trip.ticket_no,
        "status": review.status.value,
        "driver_first_name": (
            trip.driver.employee.first_name if trip.driver.employee else "-"
        ),
        "driver_last_name": (
            trip.driver.employee.last_name if trip.driver.employee else "-"
        ),
        "helpers": [
            {"id": h.id, "first_name": h.first_name, "last_name": h.last_name}
            for h in trip_helpers
        ],
        "start_photo": start_photo.file_url if start_photo else None,
        "stamped_invoice_photo": end_photo.file_url if end_photo else None,
        # origin — needed for the map's origin marker
        "origin_store": trip.origin_store.name if trip.origin_store else "-",
        "origin_lat": trip.origin_store.latitude if trip.origin_store else None,
        "origin_long": trip.origin_store.longitude if trip.origin_store else None,
        "start_time": to_ph(trip.start_time),
        "end_time": to_ph(trip.end_time),
                "stops": [
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
                "delivery_proof_photo": (
                    delivery_proof_by_stop_id.get(stop.id)
                ),
            }
            for stop in sorted_stops
        ],

        "gps_logs": gps_logs_data,

        # Coordinator review
        "coordinator_name": coordinator_name(review),
        "coordinator_remarks": review.coordinator_remarks,
        "submitted_at": to_ph(review.submitted_at),

        # Office Personnel review
        "office_reviewer_id": review.office_reviewer_id,
        "office_remarks": review.office_remarks,
        "office_reviewed_at": (
            to_ph(review.office_reviewed_at)
            if review.office_reviewed_at
            else None
        ),

        # Finance approval
        "approved_at": (
            to_ph(review.approved_at)
            if review.approved_at
            else None
        ),
    }


# =========================
# APPROVE
# =========================
@router.post("/{trip_id}/approve")
def approve_finance_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    review = (
        db.query(TripFinanceReview)
        .filter(TripFinanceReview.trip_id == trip_id)
        .first()
    )

    if not review:
        raise HTTPException(404, "Trip not submitted for finance review.")

    if review.status != FinanceReviewStatus.FINANCE_REVIEW:
        raise HTTPException(
            status_code=400,
            detail="Trip is not awaiting finance review.",
        )

    review.status = FinanceReviewStatus.APPROVED
    review.finance_reviewer_id = current_admin.id
    review.approved_at = datetime.utcnow()

    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    trip.status = TripStatus.COMPLETED
    trip.end_time = trip.end_time or datetime.utcnow()

    # TODO: hook into attendance/payroll here, e.g.:
    # sync_trip_to_payroll(trip)

    db.commit()

    return {"message": "Trip approved and synced to attendance & payroll."}