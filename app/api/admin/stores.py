# app/api/admin/stores.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from datetime import datetime

from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.models.trip_stops import TripStop
from app.models.stores import Store
from app.models.notification import Notification
from app.models.trips import Trip
from app.services.gps_service import calculate_distance_meters

router = APIRouter(prefix="/admin/stores", tags=["Admin Stores"])


class ApproveStoreRequest(BaseModel):
    name: str
    allowed_radius_meters: int = 100


# ==========================================
# GET ALL UNKNOWN STOPS (REQUIRES REVIEW)
# ==========================================
@router.get("/unknown-stops")
def get_unknown_stops(
    db: Session = Depends(get_db), current_admin=Depends(get_current_admin)
):
    """
    Returns all trip stops that were checked-in
    at unregistered store locations.
    """

    stops = (
        db.query(TripStop)
        .options(joinedload(TripStop.trip).joinedload(Trip.driver))
        .filter(TripStop.requires_review)
        .order_by(TripStop.check_in_time.desc())
        .all()
    )

    return [
        {
            "stop_id": stop.id,
            "trip_id": stop.trip_id,
            "username": stop.trip.driver.username,
            "lat_in": stop.lat_in,
            "long_in": stop.long_in,
            "check_in_time": stop.check_in_time,
        }
        for stop in stops
    ]


# ==========================================
# APPROVE UNKNOWN STOP & CREATE STORE
# ==========================================
@router.post("/approve-from-stop/{stop_id}")
def approve_store_from_stop(
    stop_id: int,
    payload: ApproveStoreRequest,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    """
    Converts an unknown trip stop into a registered store.
    """

    try:
        # ----------------------------------------
        # 1️⃣ Fetch Stop
        # ----------------------------------------
        stop = (
            db.query(TripStop)
            .filter(TripStop.id == stop_id, TripStop.requires_review)
            .first()
        )

        if not stop:
            raise HTTPException(
                status_code=404, detail="Stop not found or already approved."
            )

        if stop.lat_in is None or stop.long_in is None:
            raise HTTPException(status_code=400, detail="Invalid stop coordinates.")

        # ----------------------------------------
        # 2️⃣ Validate Payload
        # ----------------------------------------
        store_name = payload.name.strip()

        if not store_name:
            raise HTTPException(status_code=400, detail="Store name is required.")

        if payload.allowed_radius_meters <= 0:
            raise HTTPException(
                status_code=400, detail="Allowed radius must be greater than zero."
            )

        # ----------------------------------------
        # 3️⃣ Prevent Duplicate Store Name
        # ----------------------------------------
        existing_name = db.query(Store).filter(Store.name == store_name).first()

        if existing_name:
            raise HTTPException(status_code=400, detail="Store name already exists.")

        # ----------------------------------------
        # 4️⃣ Prevent Duplicate Store by Location
        # ----------------------------------------
        existing_stores = db.query(Store).all()

        for store in existing_stores:
            distance = calculate_distance_meters(
                stop.lat_in, stop.long_in, store.latitude, store.longitude
            )

            if distance <= store.allowed_radius_meters:
                raise HTTPException(
                    status_code=400, detail="A store already exists near this location."
                )

        # ----------------------------------------
        # 5️⃣ Create New Store
        # ----------------------------------------
        new_store = Store(
            name=store_name,
            latitude=stop.lat_in,
            longitude=stop.long_in,
            allowed_radius_meters=payload.allowed_radius_meters,
        )

        db.add(new_store)
        db.flush()  # 🔥 Ensures new_store.id exists before linking

        # ----------------------------------------
        # 6️⃣ Link Stop to Store
        # ----------------------------------------
        stop.store_id = new_store.id
        stop.requires_review = False

        # ----------------------------------------
        # 7️⃣ Update Related Notification
        # ----------------------------------------
        notification = (
            db.query(Notification)
            .filter(
                Notification.trip_stop_id == stop.id,
                Notification.type == "UNREGISTERED_STORE",
                Notification.status == "PENDING",
            )
            .first()
        )

        if notification:
            notification.status = "APPROVED"
            notification.reviewed_by_admin_id = current_admin.id
            notification.reviewed_at = datetime.utcnow()

        # ----------------------------------------
        # 8️⃣ Optional: Auto-resolve Nearby Unknown Stops
        # ----------------------------------------
        unknown_stops = db.query(TripStop).filter(TripStop.requires_review).all()

        for s in unknown_stops:
            if s.lat_in is None or s.long_in is None:
                continue

            distance = calculate_distance_meters(
                s.lat_in, s.long_in, new_store.latitude, new_store.longitude
            )

            if distance <= new_store.allowed_radius_meters:
                s.store_id = new_store.id
                s.requires_review = False

        # ----------------------------------------
        # 9️⃣ Commit Transaction
        # ----------------------------------------
        db.commit()

        return {
            "message": "Store approved and registered successfully.",
            "store_id": new_store.id,
            "store_name": new_store.name,
        }

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to approve and register store."
        )
