"""Change a trip's trip category after the fact.

A trip copies its store's category when it's created, so a later change to
the store doesn't quietly change old pay. These helpers move trips to a new
category on purpose -- from Edit Store (every trip to that store, picked
from a list) or one trip at a time (Trip Document).

Rules (both ways):
- never a trip whose payroll is locked;
- never to a category with no driver rate for that trip's truck (it would
  just swap one P0 for another);
- every change is logged on the trip (Remarks) with who, when, the old
  category and the reason;
- a pay run already generated keeps its saved figures until regenerated.
"""

from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.TripRate import TripRateProfile
from app.models.trip_bypass_log import TripBypassLog
from app.models.trips import Trip, TripStatus
from app.services.trip_rates import load_rules, resolve_trip_rates
from app.utils.timezone import utc_to_ph

ACTION = "change-category"

# Same people who approve trip corrections (Finance).
CHANGER_ROLES = ["admin", "superadmin"]
CHANGER_KEY = "finance.finance_trips"


def profile_label(profile) -> str | None:
    if not profile:
        return None
    return profile.profile_name or profile.code


def active_profile_or_400(db: Session, profile_id: int) -> TripRateProfile:
    profile = (
        db.query(TripRateProfile)
        .filter(TripRateProfile.id == profile_id, TripRateProfile.is_active.is_(True))
        .first()
    )
    if not profile:
        raise HTTPException(status_code=400, detail="Pick an active trip category.")
    return profile


def _trip_day(trip):
    when = trip.start_time or trip.created_at
    return utc_to_ph(when).date() if when else None


def rate_with(trip, profile, rules) -> float:
    """Driver 1st-trip rate this trip would pay under `profile`."""
    draft = SimpleNamespace(
        trip_rate_profile=profile,
        trip_rate_profile_id=profile.id,
        vehicle_unit=trip.vehicle_unit,
        origin_store_id=trip.origin_store_id,
        destination_store=trip.destination_store,
        destination_store_id=trip.destination_store_id,
        trip_helpers=list(trip.trip_helpers or []),
    )
    return float(resolve_trip_rates(draft, _trip_day(trip), rules).get("driver_first_trip_rate") or 0)


def lock_reason(db: Session, trip) -> str | None:
    from app.services.payroll_lock import ensure_trip_unlocked

    try:
        ensure_trip_unlocked(db, trip, "this trip")
    except HTTPException as error:
        return str(error.detail)
    return None


def check_trip(db: Session, trip, profile, rules) -> dict:
    """{ok, problem, new_rate} -- whether this trip can move to `profile`."""
    if trip.trip_rate_profile_id == profile.id:
        return {"ok": False, "problem": "Already this category", "new_rate": None}
    locked = lock_reason(db, trip)
    if locked:
        return {"ok": False, "problem": "Payroll locked", "new_rate": None}
    new_rate = rate_with(trip, profile, rules)
    if new_rate <= 0:
        truck = (
            trip.vehicle_unit.truck_type.name
            if trip.vehicle_unit and trip.vehicle_unit.truck_type
            else "this truck"
        )
        return {
            "ok": False,
            "problem": f"{profile_label(profile)} has no rate for {truck}",
            "new_rate": 0,
        }
    return {"ok": True, "problem": None, "new_rate": new_rate}


def trip_row(db: Session, trip, profile, rules) -> dict:
    from app.utils.user_display import display_name

    day = _trip_day(trip)
    return {
        "id": trip.id,
        "trip_code": trip.trip_code,
        "date": day.isoformat() if day else None,
        "driver": display_name(trip.driver) if trip.driver else None,
        "shipment": trip.ticket_no,
        "status": getattr(trip.status, "value", trip.status),
        "old_category": profile_label(trip.trip_rate_profile),
        "new_category": profile_label(profile),
        **check_trip(db, trip, profile, rules),
    }


def store_trips(db: Session, store_id: int) -> list[Trip]:
    """Trips whose main stop is this store (they take its category)."""
    return (
        db.query(Trip)
        .options(
            joinedload(Trip.trip_rate_profile),
            joinedload(Trip.vehicle_unit),
            joinedload(Trip.destination_store),
            joinedload(Trip.trip_helpers),
            joinedload(Trip.driver),
        )
        .filter(
            Trip.destination_store_id == store_id,
            Trip.is_archived.is_(False),
            Trip.status != TripStatus.CANCELLED,
        )
        .order_by(Trip.start_time.desc(), Trip.id.desc())
        .all()
    )


def store_preview(db: Session, store_id: int, profile) -> list[dict]:
    rules = load_rules(db)
    return [
        trip_row(db, trip, profile, rules)
        for trip in store_trips(db, store_id)
        if trip.trip_rate_profile_id != profile.id
    ]


def change(db: Session, trip, profile, user, reason: str | None, rules=None) -> dict:
    """Moves one trip to `profile` (after the checks); logs it. No commit."""
    rules = rules if rules is not None else load_rules(db)
    result = check_trip(db, trip, profile, rules)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["problem"])
    old = profile_label(trip.trip_rate_profile) or "none"
    trip.trip_rate_profile_id = profile.id
    trip.trip_rate_profile = profile
    note = f"Trip category {old} → {profile_label(profile)}"
    if (reason or "").strip():
        note += f". {reason.strip()[:500]}"
    db.add(
        TripBypassLog(
            trip_id=trip.id,
            action=ACTION,
            performed_by_user_id=user.id,
            reason=note,
        )
    )
    return {"id": trip.id, "old_category": old, "new_category": profile_label(profile)}
