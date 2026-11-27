"""Change trip categories after the fact (Edit Store / Trip Document).
See app/services/trip_category_change.py for the rules."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role_or_module
from app.models.stores import Store
from app.models.trips import Trip
from app.models.user import User
from app.services import trip_category_change as C
from app.services.trip_rates import load_rules

router = APIRouter(prefix="/admin/trip-category", tags=["Trip Category Change"])

_require_changer = require_role_or_module(roles=C.CHANGER_ROLES, module_key=C.CHANGER_KEY)


class StoreTripsChange(BaseModel):
    profile_id: int
    trip_ids: list[int]
    reason: str | None = None


class TripChange(BaseModel):
    profile_id: int
    reason: str | None = None


@router.get("/can-change")
def can_change(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        _require_changer(None, current_user, db)
        return {"can_change": True}
    except HTTPException:
        return {"can_change": False}


@router.get("/stores/{store_id}/trips")
def store_trips_preview(
    store_id: int,
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_changer),
):
    """Trips to this store not on `profile_id` yet, each with whether it
    can move (payroll not locked, the category has a rate for its truck)."""
    if not db.query(Store.id).filter(Store.id == store_id).first():
        raise HTTPException(status_code=404, detail="Store not found.")
    profile = C.active_profile_or_400(db, profile_id)
    rows = C.store_preview(db, store_id, profile)
    return {
        "category": C.profile_label(profile),
        "trips": rows,
        "movable": sum(1 for r in rows if r["ok"]),
    }


@router.post("/stores/{store_id}/trips")
def store_trips_apply(
    store_id: int,
    payload: StoreTripsChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_changer),
):
    profile = C.active_profile_or_400(db, payload.profile_id)
    wanted = set(payload.trip_ids)
    if not wanted:
        raise HTTPException(status_code=400, detail="Pick at least one trip.")
    rules = load_rules(db)
    changed, skipped = [], []
    for trip in C.store_trips(db, store_id):
        if trip.id not in wanted:
            continue
        result = C.check_trip(db, trip, profile, rules)
        if not result["ok"]:
            skipped.append({"id": trip.id, "trip_code": trip.trip_code, "problem": result["problem"]})
            continue
        changed.append(C.change(db, trip, profile, current_user, payload.reason or "From Edit Store", rules))
    db.commit()
    return {"changed": len(changed), "skipped": skipped}


@router.put("/trips/{trip_id}")
def change_trip_category(
    trip_id: int,
    payload: TripChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_changer),
):
    trip = (
        db.query(Trip)
        .options(joinedload(Trip.trip_rate_profile), joinedload(Trip.trip_helpers))
        .filter(Trip.id == trip_id)
        .first()
    )
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    profile = C.active_profile_or_400(db, payload.profile_id)
    result = C.change(db, trip, profile, current_user, payload.reason)
    db.commit()
    return {**result, "message": f"Trip category changed to {result['new_category']}."}


@router.get("/trips/{trip_id}/check")
def check_trip_change(
    trip_id: int,
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_changer),
):
    """Whether this trip can move to `profile_id` (before saving)."""
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    profile = C.active_profile_or_400(db, profile_id)
    return C.trip_row(db, trip, profile, load_rules(db))


@router.get("/search")
def search_trips(
    q: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_changer),
):
    """Trips by shipment no., ticket or trip code (any status but
    cancelled) -- the Correction page's Change Category picker."""
    from sqlalchemy import or_

    from app.models.trips import TripStatus
    from app.utils.user_display import display_name

    term = (q or "").strip()
    if len(term) < 3:
        return []
    like = f"%{term}%"
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.trip_rate_profile), joinedload(Trip.driver))
        .filter(
            Trip.is_archived.is_(False),
            Trip.status != TripStatus.CANCELLED,
            or_(
                Trip.ticket_no.ilike(like),
                Trip.shipment_numbers.ilike(like),
                Trip.trip_code.ilike(like),
            ),
        )
        .order_by(Trip.start_time.desc(), Trip.id.desc())
        .limit(15)
        .all()
    )
    return [
        {
            "id": t.id,
            "trip_code": t.trip_code,
            "ticket_no": t.ticket_no,
            "driver": display_name(t.driver) if t.driver else None,
            "date": C._trip_day(t).isoformat() if C._trip_day(t) else None,
            "category": C.profile_label(t.trip_rate_profile),
            "category_id": t.trip_rate_profile_id,
        }
        for t in trips
    ]
