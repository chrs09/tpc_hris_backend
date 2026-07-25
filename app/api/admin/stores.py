# app/api/admin/stores.py

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.models.trip_stops import TripStop
from app.models.TripRate import TripRateProfile
from app.models.stores import Store, StoreProfile
from app.models.notification import Notification
from app.models.trips import Trip
from app.services.gps_service import calculate_distance_meters

router = APIRouter(prefix="/admin/stores", tags=["Admin Stores"])

STORE_PROFILE_CHOICES = [
    StoreProfile.DP.value,
    StoreProfile.KD.value,
    StoreProfile.KA.value,
    StoreProfile.PUP.value,
    StoreProfile.WS.value,
]


class StoreBase(BaseModel):
    name: str = Field(..., min_length=1)
    latitude: float
    longitude: float
    allowed_radius_meters: int = 100
    required_helper: int = 0
    profile: str = StoreProfile.DP.value

    class Config:
        orm_mode = True


class ApproveStoreRequest(BaseModel):
    name: str = Field(..., min_length=1)
    allowed_radius_meters: int = 100
    required_helper: int = 0
    profile: str = StoreProfile.DP.value

    class Config:
        orm_mode = True


class StoreCreateRequest(BaseModel):
    name: str
    latitude: float
    longitude: float
    allowed_radius_meters: int
    required_helper: int
    trip_rate_profile_id: int          # ADD THIS
    profile: Optional[str] = None      # can stay for now, or remove if you're ready

class StoreUpdateRequest(BaseModel):
    name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    allowed_radius_meters: Optional[int] = None
    required_helper: Optional[int] = None
    trip_rate_profile_id: Optional[int] = None
    profile: Optional[str] = None

    class Config:
        orm_mode = True

class BulkStoreItem(BaseModel):
    name: str = Field(..., min_length=1)
    profile: str


class BulkStoreCreateRequest(BaseModel):
    stores: List[BulkStoreItem]


def validate_profile(profile: str) -> None:
    if profile not in STORE_PROFILE_CHOICES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid profile. "
                f"Valid choices are: {', '.join(STORE_PROFILE_CHOICES)}"
            ),
        )


def validate_store_payload(payload: StoreBase) -> None:
    if payload.allowed_radius_meters <= 0:
        raise HTTPException(
            status_code=400, detail="Allowed radius must be greater than zero."
        )

    if payload.required_helper < 0:
        raise HTTPException(
            status_code=400, detail="Required helper must be zero or greater."
        )

    # validate_profile(payload.profile)


def build_store_response(store: Store) -> dict:
    return {
        "id": store.id,
        "name": store.name,
        "latitude": store.latitude,
        "longitude": store.longitude,
        "allowed_radius_meters": store.allowed_radius_meters,
        "required_helper": store.required_helper,
        "profile": store.profile,
    }


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

        store_name = payload.name.strip()
        if not store_name:
            raise HTTPException(status_code=400, detail="Store name is required.")

        validate_store_payload(payload)

        existing_name = db.query(Store).filter(Store.name == store_name).first()
        if existing_name:
            raise HTTPException(status_code=400, detail="Store name already exists.")

        existing_stores = db.query(Store).all()
        for store in existing_stores:
            if store.latitude == 0 and store.longitude == 0:
                continue

            distance = calculate_distance_meters(
                stop.lat_in, stop.long_in, store.latitude, store.longitude
            )

            if distance <= store.allowed_radius_meters:
                raise HTTPException(
                    status_code=400, detail="A store already exists near this location."
                )

        new_store = Store(
            name=store_name,
            latitude=stop.lat_in,
            longitude=stop.long_in,
            allowed_radius_meters=payload.allowed_radius_meters,
            required_helper=payload.required_helper,
            profile=payload.profile,
        )

        db.add(new_store)
        db.flush()  # 🔥 Ensures new_store.id exists before linking

        stop.store_id = new_store.id
        stop.requires_review = False

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


# ==========================================
# GET STORE LIST
# ==========================================
@router.get("/")
def get_stores(
    db: Session = Depends(get_db), current_admin=Depends(get_current_admin)
):
    stores = db.query(Store).order_by(Store.name.asc()).all()
    return [build_store_response(store) for store in stores]


# ==========================================
# CREATE STORE
# ==========================================
# Add trip_rate_profile_id to your StoreCreateRequest / StoreUpdateRequest
# Pydantic schemas first, e.g.:
#
#   class StoreCreateRequest(BaseModel):
#       name: str
#       latitude: float
#       longitude: float
#       allowed_radius_meters: int
#       required_helper: int
#       trip_rate_profile_id: int          # NEW - replaces `profile` going forward
#       profile: Optional[str] = None      # LEGACY - kept optional for now


@router.post("/")
def create_store(
    payload: StoreCreateRequest,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    store_name = payload.name.strip()
    if not store_name:
        raise HTTPException(status_code=400, detail="Store name is required.")

    validate_store_payload(payload)

    existing_name = db.query(Store).filter(Store.name == store_name).first()
    if existing_name:
        raise HTTPException(status_code=400, detail="Store name already exists.")

    # NEW: resolve + validate the trip rate profile
    trip_rate_profile = (
        db.query(TripRateProfile)
        .filter(TripRateProfile.id == payload.trip_rate_profile_id)
        .filter(TripRateProfile.is_active.is_(True))
        .first()
    )

    if not trip_rate_profile:
        raise HTTPException(
            status_code=400, detail="Invalid or inactive trip rate profile."
        )

    is_pending_location = payload.latitude == 0 and payload.longitude == 0

    if not is_pending_location:
        existing_stores = db.query(Store).all()
        for store in existing_stores:
            if store.latitude == 0 and store.longitude == 0:
                continue

            distance = calculate_distance_meters(
                payload.latitude, payload.longitude, store.latitude, store.longitude
            )
            if distance <= store.allowed_radius_meters:
                raise HTTPException(
                    status_code=400,
                    detail="A store already exists near this location.",
                )

    new_store = Store(
        name=store_name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        allowed_radius_meters=payload.allowed_radius_meters,
        required_helper=payload.required_helper,
        trip_rate_profile_id=trip_rate_profile.id,
        # LEGACY: keep `profile` in sync for now so old code paths
        # (and any lingering references) still work during rollout.
        profile=trip_rate_profile.code,
    )

    db.add(new_store)
    db.commit()
    db.refresh(new_store)

    return build_store_response(new_store)

# admin store routes. It powers the Profile dropdown in the
# Add/Edit Store modal on the frontend.
 
@router.get("/trip-rate-profiles")
def get_trip_rate_profiles_for_admin(
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
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
            "code": profile.code,
            "profile_name": profile.profile_name,
            "helper_count": profile.helper_count,
        }
        for profile in profiles
    ]


# ==========================================
# BULK CREATE STORES
# ==========================================
@router.post("/bulk")
def bulk_create_stores(
    payload: BulkStoreCreateRequest,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    if not payload.stores:
        raise HTTPException(
            status_code=400,
            detail="No stores provided."
        )

    # Load active profiles once instead of querying for every store.
    profiles = (
        db.query(TripRateProfile)
        .filter(TripRateProfile.is_active.is_(True))
        .all()
    )

    profile_map = {
        profile.code.upper(): profile
        for profile in profiles
        if profile.code
    }

    created = []
    skipped = []
    failed = []

    # Keep track of names already processed in this request.
    processed_names = set()

    for item in payload.stores:
        store_name = item.name.strip()
        service_code = item.profile.strip().upper()

        # --------------------------------------
        # Validate name
        # --------------------------------------
        if not store_name:
            failed.append({
                "name": item.name,
                "reason": "Store name is required."
            })
            continue

        normalized_name = store_name.lower()

        # --------------------------------------
        # Duplicate inside uploaded JSON
        # --------------------------------------
        if normalized_name in processed_names:
            skipped.append({
                "name": store_name,
                "reason": "Duplicate store in import."
            })
            continue

        processed_names.add(normalized_name)

        # --------------------------------------
        # Temporary rule: DS -> DP
        # --------------------------------------
        if service_code == "DS":
            service_code = "DP"

        # --------------------------------------
        # Find trip rate profile by code
        # --------------------------------------
        trip_rate_profile = profile_map.get(service_code)

        if not trip_rate_profile:
            failed.append({
                "name": store_name,
                "profile": service_code,
                "reason": "Invalid or inactive trip rate profile."
            })
            continue

        # --------------------------------------
        # Check existing store
        # --------------------------------------
        existing_store = (
            db.query(Store)
            .filter(Store.name == store_name)
            .first()
        )

        if existing_store:
            skipped.append({
                "name": store_name,
                "reason": "Store already exists."
            })
            continue

        # --------------------------------------
        # Create pending-location store
        # --------------------------------------
        new_store = Store(
            name=store_name,

            # Pending coordinates
            latitude=0,
            longitude=0,

            allowed_radius_meters=100,

            # Take helper requirement from rate profile
            required_helper=trip_rate_profile.helper_count or 0,

            trip_rate_profile_id=trip_rate_profile.id,

            # Legacy field
            profile=trip_rate_profile.code,
        )

        db.add(new_store)

        created.append({
            "name": store_name,
            "profile": trip_rate_profile.code,
            "trip_rate_profile_id": trip_rate_profile.id,
            "required_helper": trip_rate_profile.helper_count or 0,
        })

    try:
        db.commit()

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Bulk store import failed. No stores were committed."
        )

    return {
        "message": "Bulk store import completed.",
        "total_received": len(payload.stores),
        "created_count": len(created),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "created": created,
        "skipped": skipped,
        "failed": failed,
    }

# Apply the same pattern to update_store: resolve trip_rate_profile_id the
# same way, set both trip_rate_profile_id and the legacy profile field
# together so they never drift apart during the transition period.
# ==========================================
# GET STORE DETAIL
# ==========================================
@router.get("/{store_id}")
def get_store(
    store_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    store = db.query(Store).filter(Store.id == store_id).first()

    if not store:
        raise HTTPException(status_code=404, detail="Store not found.")

    return build_store_response(store)


# ==========================================
# UPDATE STORE
# ==========================================
@router.patch("/{store_id}")
def update_store(
    store_id: int,
    payload: StoreUpdateRequest,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    store = db.query(Store).filter(Store.id == store_id).first()

    if not store:
        raise HTTPException(status_code=404, detail="Store not found.")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Store name is required.")

        existing_name = (
            db.query(Store)
            .filter(Store.name == name, Store.id != store_id)
            .first()
        )
        if existing_name:
            raise HTTPException(status_code=400, detail="Store name already exists.")

        store.name = name

    if payload.latitude is not None:
        store.latitude = payload.latitude
    if payload.longitude is not None:
        store.longitude = payload.longitude
    if payload.allowed_radius_meters is not None:
        if payload.allowed_radius_meters <= 0:
            raise HTTPException(
                status_code=400, detail="Allowed radius must be greater than zero."
            )
        store.allowed_radius_meters = payload.allowed_radius_meters
    if payload.required_helper is not None:
        if payload.required_helper < 0:
            raise HTTPException(
                status_code=400, detail="Required helper must be zero or greater."
            )
        store.required_helper = payload.required_helper

    if payload.trip_rate_profile_id is not None:
        profile = (
            db.query(TripRateProfile)
            .filter(
                TripRateProfile.id == payload.trip_rate_profile_id,
                TripRateProfile.is_active.is_(True),
            )
            .first()
        )

        if not profile:
            raise HTTPException(
                status_code=400, detail="Invalid or inactive trip rate profile."
            )

        store.trip_rate_profile_id = profile.id
        # LEGACY: keep `profile` in sync for now, same as create_store,
        # until the column is fully removed.
        store.profile = profile.code

    db.commit()
    db.refresh(store)

    return build_store_response(store)

