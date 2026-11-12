"""Fleet operations: a truck's status, its availability for dispatch, and
truck utilization.

Status (what Fleet Management and Trip Dispatch show):

  available    -- free to assign in Trip Dispatch
  assigned     -- on a dispatched trip not started yet      (from trips)
  in_transit   -- on a trip in progress                       (from trips)
  breakdown    -- breakdown / repair                          (set by Fleet)
  maintenance  -- scheduled maintenance, or an open repair record
  hold         -- restricted by fleet/admin for use           (set by Fleet)
  retired      -- inactive or not in service                  (set by Fleet)

Breakdown / maintenance / hold / retired are stored on the unit
(fleet_status) and win over trips; none of them can be dispatched.
Dashboard groups: Available, Assigned/In transit, Motorpool (breakdown,
maintenance), Not available (hold, retired).
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.trips import Trip, TripStatus
from app.models.vehicle_maintenance import VehicleMaintenance
from app.models.vehicle_unit import VehicleStatusLog, VehicleUnit
from app.utils.timezone import ph_to_utc, utc_to_ph, utc_to_ph_date

STATUSES = [
    {"key": "available", "label": "Available", "group": "available",
     "meaning": "Available for assignment in dispatch"},
    {"key": "assigned", "label": "Assigned", "group": "in_use",
     "meaning": "Assigned / planned shipment"},
    {"key": "in_transit", "label": "In transit", "group": "in_use",
     "meaning": "In route"},
    {"key": "breakdown", "label": "Breakdown", "group": "motorpool",
     "meaning": "Breakdown / repair"},
    {"key": "maintenance", "label": "Maintenance", "group": "motorpool",
     "meaning": "Scheduled maintenance"},
    {"key": "hold", "label": "Hold", "group": "not_available",
     "meaning": "Restricted by fleet/admin for use"},
    {"key": "retired", "label": "Retired", "group": "not_available",
     "meaning": "Inactive or not in service"},
]
GROUPS = [
    {"key": "available", "label": "Available"},
    {"key": "in_use", "label": "Assigned / In transit"},
    {"key": "motorpool", "label": "Motorpool"},
    {"key": "not_available", "label": "Not available"},
]
_BY_KEY = {s["key"]: s for s in STATUSES}

# Set by Fleet Management on the unit; none can be dispatched.
MANUAL_STATUSES = ("breakdown", "maintenance", "hold", "retired")
SETTABLE = ("available",) + MANUAL_STATUSES
DOWNTIME_STATUSES = ("breakdown", "maintenance", "hold")


def _fmt(dt):
    return utc_to_ph(dt).strftime("%b %d, %Y %I:%M %p") if dt else None


def unit_statuses(db: Session, units: list) -> dict:
    """{unit_id: {...}} -- the effective status of each unit right now."""
    ids = [u.id for u in units] or [0]
    trips = {}
    for trip in (
        db.query(Trip)
        .filter(
            Trip.vehicle_unit_id.in_(ids),
            Trip.status.in_([TripStatus.ASSIGNED, TripStatus.ACTIVE]),
        )
        .order_by(Trip.id.desc())
    ):
        current = trips.get(trip.vehicle_unit_id)
        # In transit wins over a later assigned trip.
        if current is None or (
            trip.status == TripStatus.ACTIVE and current.status != TripStatus.ACTIVE
        ):
            trips[trip.vehicle_unit_id] = trip
    repairs = {
        m.vehicle_unit_id: m
        for m in db.query(VehicleMaintenance)
        .filter(VehicleMaintenance.vehicle_unit_id.in_(ids), VehicleMaintenance.in_repair.is_(True))
        .order_by(VehicleMaintenance.service_date.asc())
    }

    out = {}
    for unit in units:
        manual = unit.fleet_status if unit.fleet_status in MANUAL_STATUSES else None
        if not manual and not unit.is_active:
            manual = "retired"
        trip = trips.get(unit.id)
        repair = repairs.get(unit.id)
        if manual:
            key, reason, since = manual, unit.status_reason, unit.status_since
        elif repair:
            key = "maintenance"
            reason = f"Under repair: {repair.maintenance_type}"
            since = repair.service_date
        elif trip is not None:
            key = "in_transit" if trip.status == TripStatus.ACTIVE else "assigned"
            reason = None
            since = trip.start_time if trip.status == TripStatus.ACTIVE else trip.created_at
        else:
            key, reason, since = "available", None, None
        meta = _BY_KEY[key]
        out[unit.id] = {
            "status": key,
            "status_label": meta["label"],
            "status_group": meta["group"],
            "status_reason": reason,
            "status_since": _fmt(since),
            "status_until": unit.status_until.isoformat() if unit.status_until else None,
            "trip_code": trip.trip_code if trip is not None else None,
            "trip_ticket": trip.ticket_no if trip is not None else None,
            "dispatchable": key == "available",
        }
    return out


def ensure_dispatchable(unit) -> None:
    """Breakdown / maintenance / hold / retired units can't be dispatched."""
    if unit.fleet_status in MANUAL_STATUSES:
        label = _BY_KEY[unit.fleet_status]["label"]
        why = f" ({unit.status_reason})" if unit.status_reason else ""
        name = unit.plate_number or unit.unit_code
        raise HTTPException(
            status_code=400,
            detail=f"{name} is on {label}{why} and can't be dispatched. Pick another unit.",
        )


def set_status(db: Session, unit: VehicleUnit, status: str, reason: str | None,
               until: date | None, user_id: int | None) -> None:
    """Fleet sets a unit's status; logs downtime periods for utilization."""
    if status not in SETTABLE:
        raise HTTPException(status_code=400, detail="Pick a valid status.")
    reason = (reason or "").strip() or None
    if status in ("breakdown", "hold", "retired") and not reason:
        raise HTTPException(status_code=400, detail="Enter a reason for this status.")
    if status != "available":
        busy = (
            db.query(Trip.id)
            .filter(Trip.vehicle_unit_id == unit.id, Trip.status == TripStatus.ACTIVE)
            .first()
        )
        if busy and status in ("hold", "retired", "maintenance"):
            raise HTTPException(
                status_code=400,
                detail="This unit is on a trip in progress. Wait until it's back, or use Breakdown.",
            )

    now = datetime.utcnow()
    if status != unit.fleet_status:
        for log in db.query(VehicleStatusLog).filter(
            VehicleStatusLog.vehicle_unit_id == unit.id, VehicleStatusLog.ended_at.is_(None)
        ):
            log.ended_at = now
        if status != "available":
            db.add(VehicleStatusLog(
                vehicle_unit_id=unit.id, status=status, reason=reason,
                started_at=now, created_by=user_id,
            ))
        unit.status_since = now if status != "available" else None
    elif status != "available":
        open_log = (
            db.query(VehicleStatusLog)
            .filter(VehicleStatusLog.vehicle_unit_id == unit.id, VehicleStatusLog.ended_at.is_(None))
            .first()
        )
        if open_log:
            open_log.reason = reason

    unit.fleet_status = status
    unit.status_reason = reason if status != "available" else None
    unit.status_until = until if status in ("breakdown", "maintenance", "hold") else None
    unit.status_updated_by = user_id
    # Retired units drop out of the active list (same as Deactivate).
    unit.is_active = status != "retired"


def _days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def utilization(db: Session, start: date, end: date) -> dict:
    """Per truck for start..end (PH dates): trips, days used, hours on
    trips, downtime days (breakdown / maintenance / hold / open repairs)
    and utilization = days used / days in service."""
    utc_from = ph_to_utc(datetime.combine(start, time.min))
    utc_to = ph_to_utc(datetime.combine(end + timedelta(days=1), time.min))
    period_days = (end - start).days + 1
    now = datetime.utcnow()

    units = db.query(VehicleUnit).order_by(VehicleUnit.unit_code.asc()).all()
    trips = (
        db.query(Trip)
        .filter(
            Trip.vehicle_unit_id.isnot(None),
            # Only trips that actually ran (not cancelled, not still waiting
            # to start).
            Trip.status.notin_([TripStatus.CANCELLED, TripStatus.ASSIGNED]),
            Trip.is_archived.is_(False),
            Trip.start_time >= utc_from,
            Trip.start_time < utc_to,
        )
        .all()
    )
    used_days = defaultdict(set)
    trip_count = defaultdict(int)
    hours = defaultdict(float)
    for trip in trips:
        trip_count[trip.vehicle_unit_id] += 1
        used_days[trip.vehicle_unit_id].add(utc_to_ph_date(trip.start_time))
        if trip.end_time and trip.end_time > trip.start_time:
            hours[trip.vehicle_unit_id] += (trip.end_time - trip.start_time).total_seconds() / 3600

    def mark(bucket, unit_id, s_dt, e_dt):
        first = max(utc_to_ph_date(s_dt), start)
        last = min(utc_to_ph_date(e_dt or now), end)
        for d in _days(first, last):
            bucket[unit_id].add(d)

    down_days = defaultdict(set)
    retired_days = defaultdict(set)
    for log in db.query(VehicleStatusLog).filter(
        VehicleStatusLog.started_at < utc_to,
        (VehicleStatusLog.ended_at.is_(None)) | (VehicleStatusLog.ended_at >= utc_from),
    ):
        target = retired_days if log.status == "retired" else down_days
        mark(target, log.vehicle_unit_id, log.started_at, log.ended_at)
    for repair in db.query(VehicleMaintenance).filter(
        VehicleMaintenance.service_date < utc_to,
        (VehicleMaintenance.in_repair.is_(True)) | (VehicleMaintenance.repaired_at >= utc_from),
    ):
        if repair.in_repair or repair.repaired_at:
            mark(down_days, repair.vehicle_unit_id, repair.service_date, repair.repaired_at)

    statuses = unit_statuses(db, units)
    rows = []
    for unit in units:
        retired = retired_days[unit.id] - used_days[unit.id]
        if len(retired) >= period_days and not trip_count[unit.id]:
            continue  # out of service the whole period
        down = (down_days[unit.id] - used_days[unit.id]) - retired
        in_service = max(period_days - len(retired) - len(down), 0)
        used = len(used_days[unit.id])
        rows.append({
            "vehicle_unit_id": unit.id,
            "unit_code": unit.unit_code,
            "plate_number": unit.plate_number,
            "truck_type": unit.truck_type.name if unit.truck_type else None,
            "truck_type_id": unit.truck_type_id,
            "status": statuses[unit.id]["status"],
            "status_label": statuses[unit.id]["status_label"],
            "trips": trip_count[unit.id],
            "days_used": used,
            "hours_on_trips": round(hours[unit.id], 1),
            "downtime_days": len(down),
            "idle_days": max(in_service - used, 0),
            "days_in_service": in_service,
            "utilization": round(used / in_service * 100, 1) if in_service else 0.0,
        })
    rows.sort(key=lambda r: (-r["utilization"], r["unit_code"] or ""))

    def summarize(items):
        service = sum(r["days_in_service"] for r in items)
        used = sum(r["days_used"] for r in items)
        return {
            "trucks": len(items),
            "trips": sum(r["trips"] for r in items),
            "days_used": used,
            "downtime_days": sum(r["downtime_days"] for r in items),
            "idle_days": sum(r["idle_days"] for r in items),
            "utilization": round(used / service * 100, 1) if service else 0.0,
        }

    by_type = defaultdict(list)
    for r in rows:
        by_type[r["truck_type"] or "No truck type"].append(r)
    return {
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "period_days": period_days,
        "summary": summarize(rows),
        "by_truck_type": [
            {"truck_type": name, **summarize(items)} for name, items in sorted(by_type.items())
        ],
        "units": rows,
    }
