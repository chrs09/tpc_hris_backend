"""Trip corrections (Trip Management -> Correction Requests / History).

Who: coordinators / operations request; Finance approves or rejects.
When: from the moment the trip is finished by the driver until Finance
clears it (COMPLETED), and never while the payroll covering the trip --
before or after the change -- is locked.
What: date / times, shipment numbers, driver, helpers, vehicle, start point
and destination stores (same number of stops: a delivered stop keeps its
arrival record and is only relabelled to the right store).
How: the trip changes only on approval; the values it had are kept on the
correction (`original`), so the original data is never lost. A request is
test-applied in a rolled-back transaction first, so a problem (locked
payroll, no lane rate, duplicate shipment number ...) shows at request time.
"""

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.employees import Employee
from app.models.stores import Store
from app.models.trip_helper import TripHelper
from app.models.trip_stops import TripStop
from app.models.trips import Trip, TripStatus
from app.models.user import User
from app.models.vehicle_unit import VehicleUnit
from app.utils.timezone import ph_to_utc, utc_to_ph

# Finished by the driver, not yet cleared by Finance.
CORRECTABLE = (
    TripStatus.PENDING_MANUAL_APPROVAL,
    TripStatus.PENDING_APPROVAL,
    TripStatus.PENDING_OFFICE_REVIEW,
    TripStatus.PENDING_FINANCE_REVIEW,
)

FIELDS = [
    ("start_time", "Start (checkout)"),
    ("end_time", "End (check-in)"),
    ("shipment_numbers", "Shipment numbers"),
    ("driver_id", "Driver"),
    ("helper_ids", "Helpers"),
    ("vehicle_unit_id", "Vehicle"),
    ("origin_store_id", "Start point"),
    ("destination_store_ids", "Destinations"),
]
FIELD_LABELS = dict(FIELDS)


def _ph_text(dt) -> str | None:
    return utc_to_ph(dt).strftime("%Y-%m-%dT%H:%M") if dt else None


def _parse_ph(value, label) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return ph_to_utc(datetime.strptime(str(value)[:16], "%Y-%m-%dT%H:%M"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {label} -- use date and time.")


def current_values(db: Session, trip: Trip) -> dict:
    from app.api.driver.trips import _load_planned_store_ids, _load_shipment_numbers

    return {
        "start_time": _ph_text(trip.start_time),
        "end_time": _ph_text(trip.end_time),
        "shipment_numbers": _load_shipment_numbers(trip),
        "driver_id": trip.driver_id,
        "helper_ids": sorted(
            h for (h,) in db.query(TripHelper.helper_id).filter(TripHelper.trip_id == trip.id)
        ),
        "vehicle_unit_id": trip.vehicle_unit_id,
        "origin_store_id": trip.origin_store_id,
        "destination_store_ids": _load_planned_store_ids(trip)
        or ([trip.destination_store_id] if trip.destination_store_id else []),
    }


def describe(db: Session, field: str, value) -> str:
    """A value as people read it (names, plates, store names, PH time)."""
    from app.utils.user_display import display_name

    if value in (None, "", []):
        return "-"
    if field in ("start_time", "end_time"):
        return datetime.strptime(value[:16], "%Y-%m-%dT%H:%M").strftime("%b %d, %Y %I:%M %p")
    if field == "shipment_numbers":
        return ", ".join(value)
    if field == "driver_id":
        user = db.get(User, value)
        return display_name(user) if user else f"User #{value}"
    if field == "helper_ids":
        people = {e.id: e for e in db.query(Employee).filter(Employee.id.in_(value))}
        return ", ".join(
            f"{people[i].first_name} {people[i].last_name}" if i in people else f"#{i}"
            for i in value
        )
    if field == "vehicle_unit_id":
        unit = db.get(VehicleUnit, value)
        return (unit.plate_number or unit.unit_code) if unit else f"Unit #{value}"
    if field == "origin_store_id":
        store = db.get(Store, value)
        return store.name if store else f"Store #{value}"
    if field == "destination_store_ids":
        names = {s.id: s.name for s in db.query(Store).filter(Store.id.in_(value))}
        return " → ".join(names.get(i, f"#{i}") for i in value)
    return str(value)


def check_correctable(db: Session, trip: Trip) -> None:
    from app.services.payroll_lock import ensure_trip_unlocked

    if trip.status == TripStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="This trip is already Cleared by Finance and can't be corrected.",
        )
    if trip.status not in CORRECTABLE:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only a finished trip not yet cleared by Finance can be corrected. "
                "Use Edit (assigned) or Trip Bypass (in progress) instead."
            ),
        )
    ensure_trip_unlocked(db, trip, "this trip")


def changes_only(db: Session, trip: Trip, payload: dict) -> dict:
    """The fields in `payload` whose value differs from the trip's."""
    now = current_values(db, trip)
    out = {}
    for field, _ in FIELDS:
        if field not in payload or payload[field] is None:
            continue
        value = payload[field]
        if field == "helper_ids":
            value = sorted(int(v) for v in value)
        elif field == "destination_store_ids":
            value = [int(v) for v in value]
        elif field == "shipment_numbers":
            value = [str(v).strip() for v in value if str(v).strip()]
        elif field in ("driver_id", "vehicle_unit_id", "origin_store_id"):
            value = int(value)
        elif field in ("start_time", "end_time"):
            value = str(value)[:16]
        if value != now[field]:
            out[field] = value
    return out


def apply(db: Session, trip: Trip, changes: dict, warnings: list | None = None) -> dict:
    """Changes the trip; returns the values it had for those fields.
    Raises HTTPException with what to fix. Things Finance should know but
    that don't block (e.g. the rate was kept) go into `warnings`."""
    from app.api.driver.trips import (
        MAX_SHIPMENT_NUMBERS,
        _invalid_shipment_number,
        _load_shipment_stores,
    )
    from app.services.customer_tiers import apply_plan, plan_trip
    from app.services.payroll_lock import ensure_trip_unlocked
    from app.services.user_roles import driver_user_condition

    before = current_values(db, trip)
    original = {f: before[f] for f in changes}

    # ---- times
    start = _parse_ph(changes.get("start_time", before["start_time"]), "start time")
    end = _parse_ph(changes.get("end_time", before["end_time"]), "end time")
    if start and end and end <= start:
        raise HTTPException(status_code=400, detail="The end time must be after the start time.")
    trip.start_time, trip.end_time = start, end

    # ---- driver / helpers
    driver_id = changes.get("driver_id", before["driver_id"])
    driver = db.query(User).filter(User.id == driver_id, driver_user_condition()).first()
    if not driver:
        raise HTTPException(status_code=400, detail="Pick a driver.")
    helper_ids = changes.get("helper_ids", before["helper_ids"])
    if len(helper_ids) != len(set(helper_ids)) or len(helper_ids) > 3:
        raise HTTPException(status_code=400, detail="Pick up to 3 different helpers.")
    if driver.employee_id and driver.employee_id in helper_ids:
        raise HTTPException(
            status_code=400, detail="The driver can't also be a helper on the same trip."
        )
    helpers = db.query(Employee).filter(Employee.id.in_(helper_ids or [0])).all()
    if len(helpers) != len(helper_ids) or any(
        (h.position or "").upper() != "HELPER" for h in helpers
    ):
        raise HTTPException(status_code=400, detail="Every helper must be an employee with position Helper.")
    trip.driver_id = driver.id
    if "helper_ids" in changes:
        db.query(TripHelper).filter(TripHelper.trip_id == trip.id).delete(synchronize_session=False)
        for hid in helper_ids:
            db.add(TripHelper(trip_id=trip.id, helper_id=hid))

    # ---- vehicle / start point
    vehicle = db.get(VehicleUnit, changes.get("vehicle_unit_id", before["vehicle_unit_id"]))
    if not vehicle:
        raise HTTPException(status_code=400, detail="Pick a vehicle.")
    origin = db.get(Store, changes.get("origin_store_id", before["origin_store_id"]))
    if not origin:
        raise HTTPException(status_code=400, detail="Pick a start point.")
    trip.vehicle_unit_id, trip.origin_store_id = vehicle.id, origin.id

    # ---- destinations (same number of stops; delivered stops relabelled)
    old_dest = before["destination_store_ids"]
    dest_ids = changes.get("destination_store_ids", old_dest)
    if len(dest_ids) != len(old_dest):
        raise HTTPException(
            status_code=400,
            detail=f"Keep {len(old_dest)} stop(s): a correction can change which store a stop is, not add or remove stops.",
        )
    if len(dest_ids) != len(set(dest_ids)):
        raise HTTPException(status_code=400, detail="Each destination can be picked once.")
    stores = {s.id: s for s in db.query(Store).filter(Store.id.in_(dest_ids or [0]))}
    if len(stores) != len(dest_ids):
        raise HTTPException(status_code=400, detail="A destination store wasn't found.")
    remap = dict(zip(old_dest, dest_ids))
    if "destination_store_ids" in changes:
        for stop in db.query(TripStop).filter(TripStop.trip_id == trip.id):
            if stop.store_id in remap:
                stop.store_id = remap[stop.store_id]
        trip.planned_store_ids = json.dumps(dest_ids)
        trip.destination_store_id = dest_ids[0] if dest_ids else None

    # ---- shipment numbers (renamed by position; store pairing kept)
    numbers = changes.get("shipment_numbers", before["shipment_numbers"])
    pairs = _load_shipment_stores(trip)
    special = any(str(n).startswith("ST-") for n in before["shipment_numbers"])
    if "shipment_numbers" in changes:
        if special:
            raise HTTPException(status_code=400, detail="A special trip's ST- code can't be changed.")
        if not numbers or len(numbers) > MAX_SHIPMENT_NUMBERS or len(numbers) != len(set(numbers)):
            raise HTTPException(status_code=400, detail="Enter 1 to 10 different shipment numbers.")
        bad = _invalid_shipment_number(numbers)
        if bad:
            raise HTTPException(status_code=400, detail=f'Shipment number "{bad}" must be exactly 8 digits.')
        used = set()
        for other in db.query(Trip.id, Trip.ticket_no, Trip.shipment_numbers).filter(Trip.id != trip.id):
            if "(cancelled #" in (other.ticket_no or ""):
                continue
            try:
                used.update(json.loads(other.shipment_numbers) if other.shipment_numbers else [other.ticket_no])
            except Exception:
                pass
        taken = next((n for n in numbers if n in used), None)
        if taken:
            raise HTTPException(status_code=400, detail=f'Shipment number "{taken}" is already on another trip.')
        renamed = dict(zip(before["shipment_numbers"], numbers))
        pairs = {renamed.get(k, k): v for k, v in pairs.items() if k in renamed}
        for n in numbers:
            pairs.setdefault(n, dest_ids[:1])
        trip.shipment_numbers = json.dumps(numbers)
        trip.ticket_no = ", ".join(numbers)
    if pairs:
        trip.shipment_stores = json.dumps(
            {n: [remap.get(s, s) for s in ids] for n, ids in pairs.items()}
        )

    # ---- rate (customer tier / category) for the corrected trip
    # Worked out again only when what decides it changed: the start point,
    # the vehicle or the stops. A time / shipment / crew fix keeps the
    # trip's rate as dispatched -- even if its location's trip profile was
    # turned off since (e.g. hubs whose profiles were removed).
    route_changed = any(
        k in changes for k in ("origin_store_id", "vehicle_unit_id", "destination_store_ids")
    )
    if dest_ids and route_changed:
        try:
            plan = plan_trip(
                db,
                [stores[i] for i in dest_ids],
                origin,
                vehicle,
                utc_to_ph(trip.start_time or trip.created_at).date(),
            )
            apply_plan(trip, plan)
        except HTTPException as exc:
            # The rate setup can't place the corrected route (e.g. a hub
            # whose trip profile was removed). A correction fixes what
            # happened, so it isn't blocked: the trip keeps the rate it was
            # dispatched with, and Finance sees why when approving.
            if warnings is not None:
                warnings.append(f"Rate kept from the original trip -- {exc.detail}")

    db.flush()
    # The corrected trip must not land in a locked payroll either.
    ensure_trip_unlocked(db, trip, "the corrected trip")
    return original


def dry_run(db: Session, trip: Trip, changes: dict, warnings: list | None = None) -> dict:
    """Validates a request by applying it inside a savepoint that's
    always rolled back. Returns the trip's current values for the fields."""
    nested = db.begin_nested()
    try:
        return apply(db, trip, changes, warnings)
    finally:
        nested.rollback()
        db.expire(trip)
