# app/api/admin/route_rides.py
#
# Route rides: a driver riding along on another driver's trip.
#   - Trip Assignment -> "Is Route Ride": pick the rider and the driver
#     (trip in progress) they ride with; shipments / stores / truck come
#     from that trip. The rider can do the trip's steps in their app.
#   - Route Ride Manual: rides done before this existed (no trip) -- a
#     date, how many, and the category (or an amount) -- for payroll.
# Paid like a driver trip of that category: Driver 1st / Next (or a typed
# amount per ride) -- app/services/route_ride.py.

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.route_ride import RouteRide
from app.models.stores import Store
from app.models.TripRate import TripRateProfile
from app.models.trips import Trip
from app.models.user import User, UserRole
from app.services.payroll_lock import ensure_unlocked
from app.services.route_ride import (
    IN_PROGRESS,
    busy_on_trip,
    ride_amount,
    ride_day,
    ride_rates,
)
from app.services.trip_rates import load_rules
from app.utils.user_display import display_name

router = APIRouter(prefix="/admin/route-rides", tags=["Route Rides"])

_require_trip_assignment = require_role_or_module(
    roles=["admin", "superadmin", "coordinator_admin", "coordinator"],
    module_key=["trip_management.trip_assignment", "trip_management.trips"],
)


def _load_list(value) -> list:
    import json

    try:
        data = json.loads(value) if value else []
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _trip_summary(db: Session, trip: Trip) -> dict:
    planned = [int(i) for i in _load_list(trip.planned_store_ids)]
    stores = {s.id: s.name for s in db.query(Store).filter(Store.id.in_(planned)).all()} if planned else {}
    return {
        "trip_id": trip.id,
        "trip_code": trip.trip_code,
        "driver_id": trip.driver_id,
        "driver_name": display_name(trip.driver) if trip.driver else None,
        "status": getattr(trip.status, "value", trip.status),
        "current_step": trip.current_step,
        "shipment_numbers": [str(n) for n in _load_list(trip.shipment_numbers)]
        or ([trip.ticket_no] if trip.ticket_no else []),
        "stores": [stores[i] for i in planned if i in stores],
        "origin": trip.origin_store.name if trip.origin_store else None,
        "vehicle_unit": trip.vehicle_unit.unit_code if trip.vehicle_unit else None,
        "plate_number": trip.vehicle_unit.plate_number if trip.vehicle_unit else None,
        "trip_category": trip.trip_rate_profile.profile_name if trip.trip_rate_profile else None,
    }


def _serialize(db: Session, ride: RouteRide, rules) -> dict:
    day = ride_day(ride)
    rates = ride_rates(ride, rules)
    return {
        # Driver 1st / Next of the category on that date (or the typed
        # amount); payroll picks 1st / Next with their other trips.
        "rate_first": rates["first"],
        "rate_next": rates["next"],
        "id": ride.id,
        "source": ride.source,
        "rider_user_id": ride.rider_user_id,
        "rider_name": display_name(ride.rider) if ride.rider else None,
        "ride_date": day.isoformat() if day else None,
        "quantity": ride.quantity or 1,
        "trip_rate_profile_id": ride.trip_rate_profile_id,
        "trip_category": (
            ride.trip_rate_profile.profile_name
            if ride.trip_rate_profile
            else (
                ride.trip.trip_rate_profile.profile_name
                if ride.trip and ride.trip.trip_rate_profile
                else None
            )
        ),
        "amount": float(ride.amount) if ride.amount is not None else None,
        # Estimate: as if these were their only trips that day.
        "total": round(ride_amount(ride, rules), 2),
        "notes": ride.notes,
        "created_by": display_name(ride.created_by) if ride.created_by else None,
        "created_at": ride.created_at.isoformat() if ride.created_at else None,
        "trip": _trip_summary(db, ride.trip) if ride.trip else None,
    }


def _rider(db: Session, user_id: int) -> User:
    rider = (
        db.query(User)
        .filter(User.id == user_id, User.role == UserRole.DRIVER, User.is_active.is_(True))
        .first()
    )
    if not rider:
        raise HTTPException(status_code=400, detail="Select a driver for the route ride.")
    return rider


# ---------------------------------------------------------------- hosts
@router.get("/hosts")
def list_host_trips(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_trip_assignment),
):
    """Drivers with a trip in progress -- "Select driver you will ride"."""
    trips = (
        db.query(Trip)
        .options(
            joinedload(Trip.driver),
            joinedload(Trip.vehicle_unit),
            joinedload(Trip.origin_store),
            joinedload(Trip.trip_rate_profile),
        )
        .filter(Trip.status.in_(IN_PROGRESS), Trip.is_archived.is_(False))
        .order_by(Trip.id.desc())
        .all()
    )
    return [_trip_summary(db, trip) for trip in trips]


# ---------------------------------------------------------------- assign
class AssignIn(BaseModel):
    rider_user_id: int
    trip_id: int
    notes: str | None = None


@router.post("")
def assign_route_ride(
    payload: AssignIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_trip_assignment),
):
    rider = _rider(db, payload.rider_user_id)
    trip = (
        db.query(Trip)
        .filter(Trip.id == payload.trip_id, Trip.status.in_(IN_PROGRESS))
        .with_for_update()
        .first()
    )
    if not trip:
        raise HTTPException(status_code=400, detail="That trip is no longer in progress.")
    if trip.driver_id == rider.id:
        raise HTTPException(status_code=400, detail="A driver can't ride along on their own trip.")
    if busy_on_trip(db, rider.id):
        raise HTTPException(
            status_code=400, detail="This driver already has a trip or route ride in progress."
        )

    ride = RouteRide(
        rider_user_id=rider.id,
        trip_id=trip.id,
        source="assigned",
        quantity=1,
        notes=(payload.notes or "").strip() or None,
        created_by_user_id=current_user.id,
    )
    db.add(ride)
    db.commit()
    db.refresh(ride)
    return _serialize(db, ride, load_rules(db))


# ---------------------------------------------------------------- manual
class ManualIn(BaseModel):
    rider_user_id: int
    ride_date: date
    quantity: int = 1
    # The category whose Route Ride rate it pays -- or a typed amount.
    trip_rate_profile_id: int | None = None
    amount: float | None = None
    notes: str | None = None


@router.post("/manual")
def add_manual_route_ride(
    payload: ManualIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_trip_assignment),
):
    """Route Ride Manual: rides done before route rides existed."""
    rider = _rider(db, payload.rider_user_id)
    if payload.quantity <= 0 or payload.quantity > 100:
        raise HTTPException(status_code=400, detail="How many must be between 1 and 100.")
    if payload.ride_date > datetime.utcnow().date():
        raise HTTPException(status_code=400, detail="The date can't be in the future.")
    if payload.amount is None and not payload.trip_rate_profile_id:
        raise HTTPException(status_code=400, detail="Pick the trip category or type the amount.")
    if payload.amount is not None and payload.amount < 0:
        raise HTTPException(status_code=400, detail="The amount can't be negative.")
    if payload.trip_rate_profile_id and not db.get(TripRateProfile, payload.trip_rate_profile_id):
        raise HTTPException(status_code=400, detail="Trip category not found.")
    ensure_unlocked(db, rider.employee_id, payload.ride_date, "a route ride")

    ride = RouteRide(
        rider_user_id=rider.id,
        source="manual",
        ride_date=payload.ride_date,
        quantity=payload.quantity,
        trip_rate_profile_id=payload.trip_rate_profile_id or None,
        amount=payload.amount,
        notes=(payload.notes or "").strip() or None,
        created_by_user_id=current_user.id,
    )
    db.add(ride)
    db.commit()
    db.refresh(ride)
    return _serialize(db, ride, load_rules(db))


# ---------------------------------------------------------------- edit
class EditIn(BaseModel):
    # Manual rides only (assigned ones come from the trip).
    rider_user_id: int | None = None
    ride_date: date | None = None
    quantity: int | None = None
    trip_rate_profile_id: int | None = None
    # Any ride: fixed amount per ride (null = the category rate), notes.
    amount: float | None = None
    notes: str | None = None


@router.patch("/{ride_id}")
def edit_route_ride(
    ride_id: int,
    payload: EditIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_trip_assignment),
):
    ride = db.query(RouteRide).filter(RouteRide.id == ride_id).with_for_update().first()
    if not ride:
        raise HTTPException(status_code=404, detail="Route ride not found.")
    sent = payload.model_fields_set

    # Payroll locked on the ride's current date -> no changes.
    old_day = ride_day(ride)
    if old_day and ride.rider:
        ensure_unlocked(db, ride.rider.employee_id, old_day, "this route ride")

    if ride.source == "manual":
        if "rider_user_id" in sent and payload.rider_user_id:
            ride.rider_user_id = _rider(db, payload.rider_user_id).id
        if "ride_date" in sent and payload.ride_date:
            if payload.ride_date > datetime.utcnow().date():
                raise HTTPException(status_code=400, detail="The date can't be in the future.")
            ride.ride_date = payload.ride_date
        if "quantity" in sent and payload.quantity is not None:
            if payload.quantity <= 0 or payload.quantity > 100:
                raise HTTPException(status_code=400, detail="How many must be between 1 and 100.")
            ride.quantity = payload.quantity
        if "trip_rate_profile_id" in sent:
            if payload.trip_rate_profile_id and not db.get(
                TripRateProfile, payload.trip_rate_profile_id
            ):
                raise HTTPException(status_code=400, detail="Trip category not found.")
            ride.trip_rate_profile_id = payload.trip_rate_profile_id or None
    elif sent & {"rider_user_id", "ride_date", "quantity", "trip_rate_profile_id"}:
        raise HTTPException(
            status_code=400,
            detail=(
                "An assigned route ride's driver, date and trip come from the trip. "
                "Remove it and assign again to change them."
            ),
        )

    if "amount" in sent:
        if payload.amount is not None and payload.amount < 0:
            raise HTTPException(status_code=400, detail="The amount can't be negative.")
        ride.amount = payload.amount
    if "notes" in sent:
        ride.notes = (payload.notes or "").strip() or None

    if ride.source == "manual" and ride.amount is None and not ride.trip_rate_profile_id:
        raise HTTPException(status_code=400, detail="Pick the trip category or type the amount.")

    # And locked on the new date / rider.
    db.flush()
    db.refresh(ride)
    new_day = ride_day(ride)
    if new_day and ride.rider:
        ensure_unlocked(db, ride.rider.employee_id, new_day, "this route ride")

    db.commit()
    db.refresh(ride)
    return _serialize(db, ride, load_rules(db))


# ---------------------------------------------------------------- list / remove
@router.get("")
def list_route_rides(
    start: date | None = Query(None),
    end: date | None = Query(None),
    rider_user_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_trip_assignment),
):
    query = db.query(RouteRide).options(
        joinedload(RouteRide.rider),
        joinedload(RouteRide.trip),
        joinedload(RouteRide.trip_rate_profile),
    )
    if rider_user_id:
        query = query.filter(RouteRide.rider_user_id == rider_user_id)
    rides = query.order_by(RouteRide.id.desc()).limit(500).all()
    rules = load_rules(db)
    out = []
    for ride in rides:
        day = ride_day(ride)
        if start and (day is None or day < start):
            continue
        if end and (day is None or day > end):
            continue
        out.append(_serialize(db, ride, rules))
    return out


@router.delete("/{ride_id}")
def remove_route_ride(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_trip_assignment),
):
    ride = db.query(RouteRide).filter(RouteRide.id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail="Route ride not found.")
    day = ride_day(ride)
    if day and ride.rider:
        ensure_unlocked(db, ride.rider.employee_id, day, "this route ride")
    db.delete(ride)
    db.commit()
    return {"message": "Route ride removed."}
