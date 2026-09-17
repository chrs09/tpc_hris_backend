# app/api/admin/origins.py
#
# Origins (hubs/yards a driver dispatches FROM) used to only be
# manageable as a buried "is_hub" checkbox on the general Customers
# (Store) page. This gives them their own dedicated page under Trip
# Management instead -- but they're still the same underlying Store
# rows (Store.is_hub = True), not a separate table, since is_hub is
# already the real, deeply-wired concept everywhere a trip's origin
# matters: dispatch_trip's origin_store_id validation, checkin_trip's
# hub geofence check, and get_available_stores' hub exclusion (see
# app/api/driver/trips.py). A separate table would duplicate that
# concept and risk drifting out of sync with it.
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.stores import Store

router = APIRouter(prefix="/admin/origins", tags=["Admin Origins"])


class OriginCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    latitude: float
    longitude: float
    allowed_radius_meters: int = 150


class OriginUpdateRequest(BaseModel):
    name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    allowed_radius_meters: Optional[int] = None


def _build_origin_response(store: Store) -> dict:
    return {
        "id": store.id,
        "name": store.name,
        "latitude": store.latitude,
        "longitude": store.longitude,
        "allowed_radius_meters": store.allowed_radius_meters,
    }


@router.get("/")
def get_origins(
    db: Session = Depends(get_db),
    current_admin=Depends(
        require_role_or_module(
            roles=["admin", "superadmin", "coordinator_admin", "coordinator"],
            module_key="trip_management.origins",
        )
    ),
):
    origins = (
        db.query(Store)
        .filter(Store.is_hub.is_(True))
        .order_by(Store.name.asc())
        .all()
    )
    return [_build_origin_response(store) for store in origins]


@router.post("/")
def create_origin(
    payload: OriginCreateRequest,
    db: Session = Depends(get_db),
    current_admin=Depends(
        require_role_or_module(
            roles=["admin", "superadmin", "coordinator_admin"],
            module_key="trip_management.origins",
        )
    ),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Origin name is required.")

    if payload.allowed_radius_meters <= 0:
        raise HTTPException(
            status_code=400, detail="Allowed radius must be greater than zero."
        )

    existing = db.query(Store).filter(Store.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="A store/origin with this name already exists.")

    origin = Store(
        name=name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        allowed_radius_meters=payload.allowed_radius_meters,
        required_helper=0,
        is_hub=True,
    )
    db.add(origin)
    db.commit()
    db.refresh(origin)

    return _build_origin_response(origin)


@router.patch("/{origin_id}")
def update_origin(
    origin_id: int,
    payload: OriginUpdateRequest,
    db: Session = Depends(get_db),
    current_admin=Depends(
        require_role_or_module(
            roles=["admin", "superadmin", "coordinator_admin"],
            module_key="trip_management.origins",
        )
    ),
):
    origin = (
        db.query(Store)
        .filter(Store.id == origin_id, Store.is_hub.is_(True))
        .first()
    )
    if not origin:
        raise HTTPException(status_code=404, detail="Origin not found.")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Origin name is required.")
        existing = (
            db.query(Store)
            .filter(Store.name == name, Store.id != origin_id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400, detail="A store/origin with this name already exists."
            )
        origin.name = name

    if payload.latitude is not None:
        origin.latitude = payload.latitude
    if payload.longitude is not None:
        origin.longitude = payload.longitude
    if payload.allowed_radius_meters is not None:
        if payload.allowed_radius_meters <= 0:
            raise HTTPException(
                status_code=400, detail="Allowed radius must be greater than zero."
            )
        origin.allowed_radius_meters = payload.allowed_radius_meters

    db.commit()
    db.refresh(origin)

    return _build_origin_response(origin)
