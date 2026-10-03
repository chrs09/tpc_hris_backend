# app/api/admin/delivery_summary.py
#
# Delivery Summary -- the monthly Coca-Cola delivery report (the "Tytan
# Prime Coca-Cola Delivery Summary" spreadsheet), built from the trips
# instead of typed by hand:
#   * Total Trips Summary: trips per driver and truck type, per location
#     (origin) and truck type, and per day.
#   * "<truck type> Records": one row per driver per day -- origin,
#     plate, category, helpers, Yes / Absent / LEAVE, first dispatch time,
#     last return time and the number of trips that day.
# Counts every started trip in the month that wasn't cancelled.

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.attendance import AttendanceRecord
from app.models.employees import Employee
from app.models.stores import Store
from app.models.truck_type import TruckType
from app.models.trip_helper import TripHelper
from app.models.trips import Trip, TripStatus
from app.models.user import User, UserRole
from app.models.vehicle_unit import VehicleUnit
from app.utils.user_display import display_name

router = APIRouter(prefix="/admin/delivery-summary", tags=["Delivery Summary"])

_require_access = require_role_or_module(
    roles=["admin", "coordinator_admin", "coordinator"],
    module_key="trip_management.delivery_summary",
)

PH = timedelta(hours=8)
NO_TRUCK_TYPE = "No truck type"


def _month_bounds(month: str) -> tuple[date, date]:
    try:
        first = datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Month must look like 2026-06.")
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def _hhmm(dt: datetime | None) -> str | None:
    return (dt + PH).strftime("%I:%M %p").lstrip("0") if dt else None


@router.get("")
def get_delivery_summary(
    month: str = Query(..., description="YYYY-MM"),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_access),
):
    first, last = _month_bounds(month)
    start_utc = datetime.combine(first, datetime.min.time()) - PH
    end_utc = datetime.combine(last + timedelta(days=1), datetime.min.time()) - PH

    trips = (
        db.query(Trip)
        .options(
            joinedload(Trip.driver).joinedload(User.employee),
            joinedload(Trip.vehicle_unit).joinedload(VehicleUnit.truck_type),
            joinedload(Trip.origin_store),
            joinedload(Trip.trip_rate_profile),
            joinedload(Trip.trip_helpers).joinedload(TripHelper.helper),
        )
        .filter(
            Trip.start_time.isnot(None),
            Trip.start_time >= start_utc,
            Trip.start_time < end_utc,
            Trip.status != TripStatus.CANCELLED,
        )
        .order_by(Trip.start_time.asc())
        .all()
    )

    # Only active employees -- an inactive employee (or disabled account)
    # is left out of every list and total.
    def _active(user) -> bool:
        return bool(
            user
            and user.is_active
            and (user.employee is None or user.employee.is_active == 1)
        )

    trips = [trip for trip in trips if _active(trip.driver)]

    # ---- one record per driver, per day, per truck actually used (a
    # driver who switched trucks that day has a row on each truck's tab)
    days: dict[tuple, dict] = {}
    driver_trucks: dict[int, Counter] = defaultdict(Counter)
    for trip in trips:
        day = (trip.start_time + PH).date()
        vehicle = trip.vehicle_unit
        truck = (
            vehicle.truck_type.name
            if vehicle and vehicle.truck_type
            else NO_TRUCK_TYPE
        )
        driver_trucks[trip.driver_id][truck] += 1
        row = days.setdefault(
            (day, trip.driver_id, truck),
            {
                "date": str(day),
                "driver_id": trip.driver_id,
                "driver": display_name(trip.driver) if trip.driver else None,
                "origin": trip.origin_store.name if trip.origin_store else None,
                "plate": (vehicle.plate_number or vehicle.unit_code) if vehicle else None,
                "truck_type": truck,
                "categories": [],
                "helpers": [],
                "status": "Yes",
                "first_time": _hhmm(trip.start_time),
                "last_time": None,
                "trips": 0,
                "_last_end": None,
            },
        )
        row["trips"] += 1
        profile = trip.trip_rate_profile
        category = (profile.code or profile.profile_name) if profile else None
        if category and category not in row["categories"]:
            row["categories"].append(category)
        for th in trip.trip_helpers:
            if th.helper:
                name = f"{th.helper.first_name} {th.helper.last_name}"
                if name not in row["helpers"]:
                    row["helpers"].append(name)
        if trip.end_time and (row["_last_end"] is None or trip.end_time > row["_last_end"]):
            row["_last_end"] = trip.end_time
            row["last_time"] = _hhmm(trip.end_time)

    # ---- driver-days with no trip but Absent / On Leave (the sheet lists them)
    drivers = {
        u.id: u
        for u in db.query(User).options(joinedload(User.employee)).filter(User.id.in_(driver_trucks.keys() or [0]))
    }
    by_employee = {u.employee_id: u for u in drivers.values() if u.employee_id}
    if by_employee:
        for rec in db.query(AttendanceRecord).filter(
            AttendanceRecord.employee_id.in_(by_employee.keys()),
            AttendanceRecord.attendance_date >= first,
            AttendanceRecord.attendance_date <= last,
            AttendanceRecord.status.in_(["Absent", "On Leave"]),
        ):
            user = by_employee[rec.employee_id]
            if any(k[0] == rec.attendance_date and k[1] == user.id for k in days):
                continue
            usual_truck = driver_trucks[user.id].most_common(1)[0][0]
            days[(rec.attendance_date, user.id, usual_truck)] = {
                "date": str(rec.attendance_date),
                "driver_id": user.id,
                "driver": display_name(user),
                "origin": None,
                "plate": None,
                # Their usual truck this month, so they land on its tab.
                "truck_type": usual_truck,
                "categories": [],
                "helpers": [],
                "status": "LEAVE" if rec.status == "On Leave" else "Absent",
                "first_time": None,
                "last_time": None,
                "trips": 0,
                "_last_end": None,
            }

    per_driver_day: dict[tuple, list] = defaultdict(list)
    for (day, driver_id, truck), row in days.items():
        if row["trips"]:
            per_driver_day[(day, driver_id)].append((truck, row["trips"]))
    for (day, driver_id, truck), row in days.items():
        row["other_trucks"] = [
            {"truck_type": t, "trips": n}
            for t, n in per_driver_day[(day, driver_id)]
            if t != truck
        ]

    records: dict[str, list] = defaultdict(list)
    for row in sorted(days.values(), key=lambda r: (r["date"], r["first_time"] or "~", r["driver"] or "")):
        row.pop("_last_end", None)
        records[row["truck_type"]].append(row)

    # ---- summaries (the sheet lists every driver / location / day, 0s too)
    per_driver = Counter()
    per_location = Counter()
    per_day = Counter()
    per_day_location = defaultdict(set)
    for trip in trips:
        vehicle = trip.vehicle_unit
        truck = vehicle.truck_type.name if vehicle and vehicle.truck_type else NO_TRUCK_TYPE
        per_driver[(trip.driver_id, truck)] += 1
        origin = trip.origin_store.name if trip.origin_store else "Unknown"
        per_location[(origin, truck)] += 1
        day = str((trip.start_time + PH).date())
        per_day[day] += 1
        per_day_location[day].add(origin)

    truck_types = [
        t.name
        for t in db.query(TruckType)
        .filter(TruckType.is_active.is_(True))
        .order_by(TruckType.name.asc())
    ]
    for t in records:
        if t not in truck_types:
            truck_types.append(t)

    # Every active driver: under this month's truck(s), else the truck of
    # their latest trip, else "No truck type".
    all_drivers = [
        user
        for user in db.query(User)
        .options(joinedload(User.employee))
        .filter(User.role == UserRole.DRIVER, User.is_active.is_(True))
        .all()
        if _active(user)
    ]
    latest_truck = {}
    for driver_id, truck_name in (
        db.query(Trip.driver_id, TruckType.name)
        .join(VehicleUnit, VehicleUnit.id == Trip.vehicle_unit_id)
        .join(TruckType, TruckType.id == VehicleUnit.truck_type_id)
        .filter(Trip.start_time.isnot(None))
        .order_by(Trip.start_time.asc())
    ):
        latest_truck[driver_id] = truck_name
    driver_rows = []
    seen = set()
    for (driver_id, truck), n in per_driver.items():
        seen.add(driver_id)
        user = drivers.get(driver_id) or db.get(User, driver_id)
        driver_rows.append(
            {
                "driver_id": driver_id,
                "driver": display_name(user) if user else "Unknown",
                "truck_type": truck,
                "trips": n,
            }
        )
    for user in all_drivers:
        if user.id not in seen:
            driver_rows.append(
                {
                    "driver_id": user.id,
                    "driver": display_name(user),
                    "truck_type": latest_truck.get(user.id, NO_TRUCK_TYPE),
                    "trips": 0,
                }
            )
    if any(r["truck_type"] == NO_TRUCK_TYPE for r in driver_rows) and NO_TRUCK_TYPE not in truck_types:
        truck_types.append(NO_TRUCK_TYPE)
    order = {t: i for i, t in enumerate(truck_types)}
    driver_rows.sort(key=lambda r: (order.get(r["truck_type"], 99), -r["trips"], r["driver"] or ""))

    # Every hub x truck type (0 when nothing went out).
    hubs = [h.name for h in db.query(Store).filter(Store.is_hub.is_(True)).order_by(Store.name)]
    location_names = hubs + sorted({loc for loc, _ in per_location} - set(hubs))
    location_rows = [
        {"location": loc, "truck_type": t, "trips": per_location.get((loc, t), 0)}
        for t in truck_types
        for loc in location_names
        if per_location.get((loc, t), 0) or t != NO_TRUCK_TYPE
    ]

    untyped = Counter()
    for trip in trips:
        vehicle = trip.vehicle_unit
        if not (vehicle and vehicle.truck_type):
            label = (vehicle.unit_code or vehicle.plate_number) if vehicle else "No vehicle"
            untyped[(vehicle.id if vehicle else None, label)] += 1

    all_days = [str(first + timedelta(days=i)) for i in range((last - first).days + 1)]
    hub_label = " + ".join(hubs) if hubs else ""

    return {
        "month": month,
        "total_trips": len(trips),
        "truck_types": truck_types,
        "by_driver": driver_rows,
        "by_location": location_rows,
        "by_day": [
            {
                "date": d,
                "location": " + ".join(sorted(per_day_location[d])) if per_day_location[d] else hub_label,
                "trips": per_day.get(d, 0),
            }
            for d in all_days
        ],
        "records": {t: records.get(t, []) for t in truck_types},
        # Trips on vehicles without a truck type (set it in Fleet).
        "no_truck_type": [
            {"vehicle_id": vid, "vehicle": label, "trips": n}
            for (vid, label), n in sorted(untyped.items(), key=lambda x: -x[1])
        ],
    }
