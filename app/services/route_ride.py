"""Route ride helpers (app/models/route_ride.py).

A route rider rides along on another driver's trip in progress. They see
that trip in their app and can do every step (whoever taps first); GPS is
tracked from the driver's phone. Paid like a driver trip of that category:
Driver 1st if it's the rider's first trip that day, else Driver Next (or a
typed amount per ride). Manual entries count `quantity` rides.
"""

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.route_ride import RouteRide
from app.models.trips import Trip, TripStatus
from app.services.trip_rates import category_rates, resolve_trip_rates
from app.utils.timezone import utc_to_ph_date

IN_PROGRESS = (TripStatus.ASSIGNED, TripStatus.ACTIVE)


def ridden_trip_ids(user_id: int):
    return select(RouteRide.trip_id).where(
        RouteRide.rider_user_id == user_id, RouteRide.trip_id.isnot(None)
    )


def on_my_trip(user_id: int):
    """Filter: trips this user drives OR rides on (route ride)."""
    return or_(Trip.driver_id == user_id, Trip.id.in_(ridden_trip_ids(user_id)))


def my_role(trip: Trip, user_id: int) -> str:
    return "driver" if trip.driver_id == user_id else "route_rider"


def busy_on_trip(db: Session, user_id: int, exclude_trip_id: int | None = None):
    """The in-progress trip this user drives or rides on, if any."""
    query = db.query(Trip.id).filter(on_my_trip(user_id), Trip.status.in_(IN_PROGRESS))
    if exclude_trip_id:
        query = query.filter(Trip.id != exclude_trip_id)
    return query.first()


def riders_of(db: Session, trip_ids) -> dict[int, list]:
    """{trip_id: [RouteRide, ...]} for assigned rides on these trips."""
    out: dict[int, list] = {}
    ids = [i for i in trip_ids if i]
    if not ids:
        return out
    for ride in db.query(RouteRide).filter(RouteRide.trip_id.in_(ids)).all():
        out.setdefault(ride.trip_id, []).append(ride)
    return out


def ride_day(ride: RouteRide) -> date | None:
    if ride.trip is not None and ride.trip.start_time:
        return utc_to_ph_date(ride.trip.start_time)
    return ride.ride_date


def ride_rates(ride: RouteRide, rules) -> dict:
    """{"first", "next", "fixed"}: the category's Driver 1st / Next rates on
    the ride's date (the trip's own rate when it rode on a trip), or the
    typed amount per ride (`fixed`, paid for every ride that day)."""
    if ride.amount is not None:
        return {"first": float(ride.amount), "next": float(ride.amount), "fixed": float(ride.amount)}
    day = ride_day(ride)
    rates = None
    if ride.trip is not None:
        rates = resolve_trip_rates(ride.trip, day, rules)
    elif ride.trip_rate_profile is not None and day is not None:
        rates = category_rates(ride.trip_rate_profile, rules, day)
    if not rates:
        return {"first": 0.0, "next": 0.0, "fixed": None}
    return {
        "first": float(rates["driver_first_trip_rate"]),
        "next": float(rates["driver_next_trip_rate"]),
        "fixed": None,
    }


def ride_amount(ride: RouteRide, rules) -> float:
    """Estimate for lists: as if these were the rider's only trips that day
    (1st, then Next). Payroll decides 1st / Next with their other trips."""
    rates = ride_rates(ride, rules)
    quantity = ride.quantity or 1
    return rates["first"] + rates["next"] * (quantity - 1)
