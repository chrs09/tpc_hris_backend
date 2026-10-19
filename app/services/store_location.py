"""Store coordinates from where drivers actually unload.

Each unloading photo's GPS is saved on its stop (TripStop.lat_unload /
long_unload). From those points:

- A store with no coordinates (blank or 0,0) takes the first good point.
- A store with coordinates moves only when the recent points agree:
  MIN_SAMPLES+ points from MIN_DRIVERS+ drivers within CLUSTER_RADIUS_M of
  each other, and their center is more than MIN_MOVE_M from the saved
  spot. One bad reading, or one driver unloading elsewhere, can't move it.
- Anything short of that is offered as a suggestion on Customers ->
  Location history, where a coordinator can accept it.

Every change is logged (StoreLocationChange) with the old and new spot.
"""

from datetime import datetime
from statistics import median

from sqlalchemy.orm import Session

from app.models.store_location_change import StoreLocationChange
from app.models.trip_stops import TripStop
from app.models.trips import Trip
from app.services.gps_service import calculate_distance_meters

LOOKBACK_POINTS = 10
MAX_ACCURACY_M = 100  # readings less accurate than this are ignored
CLUSTER_RADIUS_M = 50
MIN_SAMPLES = 3
MIN_DRIVERS = 2
MIN_MOVE_M = 25
SUGGEST_FROM_M = 50

SOURCE_LABELS = {
    "AUTO_FIRST": "Set from the first unloading photo (store had no location)",
    "AUTO_CONSENSUS": "Updated from drivers' unloading photos",
    "SUGGESTION_ACCEPTED": "Suggested location accepted",
    "MANUAL": "Edited by hand",
}


def has_location(store) -> bool:
    return (
        store.latitude is not None
        and store.longitude is not None
        and not (store.latitude == 0 and store.longitude == 0)
    )


def recent_points(db: Session, store_id: int, limit: int = LOOKBACK_POINTS) -> list[dict]:
    rows = (
        db.query(TripStop, Trip)
        .join(Trip, Trip.id == TripStop.trip_id)
        .filter(
            TripStop.store_id == store_id,
            TripStop.lat_unload.isnot(None),
            TripStop.long_unload.isnot(None),
        )
        .order_by(TripStop.unload_at.desc(), TripStop.id.desc())
        .limit(limit)
        .all()
    )
    points = []
    for stop, trip in rows:
        driver = trip.driver
        points.append(
            {
                "stop_id": stop.id,
                "trip_id": trip.id,
                "trip_code": trip.trip_code,
                "lat": stop.lat_unload,
                "long": stop.long_unload,
                "accuracy_m": stop.unload_accuracy_m,
                "at": stop.unload_at,
                "driver_id": trip.driver_id,
                "driver_name": (
                    (driver.employee and f"{driver.employee.first_name} {driver.employee.last_name}")
                    or driver.username
                )
                if driver
                else None,
            }
        )
    return points


def _usable(point) -> bool:
    return point["accuracy_m"] is None or point["accuracy_m"] <= MAX_ACCURACY_M


def measure(points: list[dict]) -> dict | None:
    """Where the recent good points agree: center, how many, how many
    drivers. None when there are no usable points."""
    good = [p for p in points if _usable(p)]
    if not good:
        return None
    mid_lat = median(p["lat"] for p in good)
    mid_long = median(p["long"] for p in good)
    cluster = [
        p
        for p in good
        if calculate_distance_meters(p["lat"], p["long"], mid_lat, mid_long) <= CLUSTER_RADIUS_M
    ]
    if not cluster:
        return None
    return {
        "lat": sum(p["lat"] for p in cluster) / len(cluster),
        "long": sum(p["long"] for p in cluster) / len(cluster),
        "samples": len(cluster),
        "drivers": len({p["driver_id"] for p in cluster}),
        "ignored": len(points) - len(cluster),
    }


def set_location(
    db: Session,
    store,
    lat: float,
    long: float,
    source: str,
    user=None,
    samples: int | None = None,
    drivers: int | None = None,
    note: str | None = None,
):
    db.add(
        StoreLocationChange(
            store_id=store.id,
            old_latitude=store.latitude if has_location(store) else None,
            old_longitude=store.longitude if has_location(store) else None,
            new_latitude=lat,
            new_longitude=long,
            source=source,
            sample_count=samples,
            driver_count=drivers,
            note=note,
            changed_by_user_id=user.id if user else None,
            created_at=datetime.utcnow(),
        )
    )
    store.latitude = lat
    store.longitude = long


def update_from_unloading(db: Session, store) -> str | None:
    """Run after an unloading photo is saved. Returns the change source
    when the store moved, else None."""
    if store is None or store.is_hub:
        return None
    points = recent_points(db, store.id)
    if not has_location(store):
        first = next((p for p in points if _usable(p)), None)
        if first:
            set_location(db, store, first["lat"], first["long"], "AUTO_FIRST", samples=1, drivers=1)
            return "AUTO_FIRST"
        return None

    m = measure(points)
    if not m or m["samples"] < MIN_SAMPLES or m["drivers"] < MIN_DRIVERS:
        return None
    moved = calculate_distance_meters(m["lat"], m["long"], store.latitude, store.longitude)
    if moved <= MIN_MOVE_M:
        return None
    set_location(
        db,
        store,
        m["lat"],
        m["long"],
        "AUTO_CONSENSUS",
        samples=m["samples"],
        drivers=m["drivers"],
        note=f"Moved {int(moved)} m to where {m['samples']} unloading photos agree.",
    )
    return "AUTO_CONSENSUS"


def suggestion(db: Session, store) -> dict | None:
    """The measured spot when it's far from the saved one but not enough
    agreement to move it automatically."""
    m = measure(recent_points(db, store.id))
    if not m:
        return None
    if not has_location(store):
        return {**m, "distance_m": None}
    distance = calculate_distance_meters(m["lat"], m["long"], store.latitude, store.longitude)
    if distance < SUGGEST_FROM_M:
        return None
    return {**m, "distance_m": int(distance)}
