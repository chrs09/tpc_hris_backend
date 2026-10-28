# app/services/incentives.py
#
# Incentive Policies: settings for each rule type and what each driver /
# helper earns under a program (app/models/incentive_program.py). Rules
# from memos 26-005 / 26-006 and Jessan:
#   trip_tiers          -- only COMPLETED trips count, Sundays included;
#                          the highest tier reached is paid.
#   daily_cash          -- Mon-Sat only; the Nth trip of the day earns
#                          trip_amounts[N-1] (the last one repeats); with
#                          first_trip_before the 1st trip only earns when
#                          it started before that time.
#   long_distance       -- the trip's farthest destination (km from the
#                          area list, else straight line from the trip's
#                          origin / the default hub) picks a km range;
#                          helpers get the base, the driver base + extra.
#   complete_attendance -- every workday present (approved leave and
#                          holidays don't break it); bonus % of the
#                          base, weekday holidays worked x2, Saturdays
#                          +30% when the base is the daily rate.
# A trip's day is the PH date it started (same as payroll / route rides).

import json
import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session, joinedload

from app.models.app_setting import AppSetting
from app.models.attendance import AttendanceRecord
from app.models.employees import Employee
from app.models.holiday import Holiday
from app.models.leave_request import LeaveRequest
from app.models.stores import Store
from app.models.trip_helper import TripHelper
from app.models.trips import Trip, TripStatus
from app.models.user import User
from app.utils.timezone import ph_to_utc, utc_to_ph

APPLIES_TO = ("drivers", "helpers")

RULE_TYPES = {
    "trip_tiers": {
        "label": "Trip Target (Tiered)",
        "defaults": {
            "include_sundays": True,
            "tiers": [
                {"name": "Tier 1", "min_trips": 65, "amount": 8000},
                {"name": "Tier 2", "min_trips": 52, "amount": 5000},
                {"name": "Tier 3", "min_trips": 39, "amount": 3000},
            ],
        },
    },
    "daily_cash": {
        "label": "Daily Cash Incentive",
        "defaults": {
            "days": [0, 1, 2, 3, 4, 5],
            "trip_amounts": [100, 100],
            "repeat_last": True,
            "first_trip_before": "06:00",
            "exclude_categories": [],
        },
    },
    "long_distance": {
        "label": "Long Distance",
        "defaults": {
            "ranges": [],
            "area_km": {},
            "use_gps_distance": True,
        },
    },
    "complete_attendance": {
        "label": "Complete Attendance",
        "defaults": {
            "bonus_percent": 20,
            "base": "daily_rate",
            "base_amount": 0,
            "workdays": [0, 1, 2, 3, 4, 5],
            "holiday_multiplier": 2,
            "saturday_premium_percent": 30,
            "leave_counts_as_present": True,
        },
    },
}

ATTENDANCE_BASES = ("daily_rate", "monthly_basic", "fixed")


class IncentiveSettingsError(ValueError):
    pass


# --- settings ----------------------------------------------------------


def _num(value, label, minimum=0):
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise IncentiveSettingsError(f"{label} must be a number.")
    if n < minimum:
        raise IncentiveSettingsError(f"{label} can't be below {minimum}.")
    return n


def _weekdays(value, label):
    if not isinstance(value, list) or any(
        not isinstance(d, int) or d < 0 or d > 6 for d in value
    ):
        raise IncentiveSettingsError(f"{label} must be weekdays 0 (Mon) to 6 (Sun).")
    return sorted(set(value))


def _hhmm(value, label):
    if value in (None, ""):
        return None
    try:
        datetime.strptime(value, "%H:%M")
    except (TypeError, ValueError):
        raise IncentiveSettingsError(f"{label} must be HH:MM (e.g. 06:00).")
    return value


def clean_settings(rule_type: str, settings: dict | None) -> dict:
    """The type's defaults with `settings` laid over, checked. Raises
    IncentiveSettingsError with a message for the page."""
    if rule_type not in RULE_TYPES:
        raise IncentiveSettingsError("Unknown incentive type.")
    s = {**RULE_TYPES[rule_type]["defaults"], **(settings or {})}

    if rule_type == "trip_tiers":
        tiers = []
        for i, t in enumerate(s.get("tiers") or [], start=1):
            tiers.append({
                "name": str(t.get("name") or f"Tier {i}").strip()[:40],
                "min_trips": int(_num(t.get("min_trips"), f"Tier {i} trips", 1)),
                "amount": _num(t.get("amount"), f"Tier {i} amount"),
            })
        if not tiers:
            raise IncentiveSettingsError("Add at least one tier.")
        tiers.sort(key=lambda t: t["min_trips"], reverse=True)
        return {"include_sundays": bool(s.get("include_sundays")), "tiers": tiers}

    if rule_type == "daily_cash":
        amounts = [_num(a, f"Trip {i} amount") for i, a in enumerate(s.get("trip_amounts") or [], start=1)]
        if not amounts:
            raise IncentiveSettingsError("Set the amount for at least the 1st trip.")
        return {
            "days": _weekdays(s.get("days"), "Applicable days"),
            "trip_amounts": amounts,
            "repeat_last": bool(s.get("repeat_last")),
            "first_trip_before": _hhmm(s.get("first_trip_before"), "First trip before"),
            "exclude_categories": [
                str(c).strip() for c in (s.get("exclude_categories") or []) if str(c).strip()
            ],
        }

    if rule_type == "long_distance":
        ranges = []
        for i, r in enumerate(s.get("ranges") or [], start=1):
            min_km = _num(r.get("min_km"), f"Range {i} from (km)")
            max_km = r.get("max_km")
            max_km = None if max_km in (None, "") else _num(max_km, f"Range {i} to (km)")
            if max_km is not None and max_km <= min_km:
                raise IncentiveSettingsError(f"Range {i}: 'to' km must be above 'from' km.")
            ranges.append({
                "label": str(r.get("label") or f"{min_km:g}+ km").strip()[:60],
                "min_km": min_km,
                "max_km": max_km,
                "helper_amount": _num(r.get("helper_amount"), f"Range {i} base amount"),
                "driver_extra": _num(r.get("driver_extra"), f"Range {i} driver extra"),
            })
        ranges.sort(key=lambda r: r["min_km"])
        area_km = {}
        for area, km in (s.get("area_km") or {}).items():
            if str(area).strip():
                area_km[str(area).strip()] = _num(km, f"Km for {area}")
        return {"ranges": ranges, "area_km": area_km, "use_gps_distance": bool(s.get("use_gps_distance"))}

    # complete_attendance
    if s.get("base") not in ATTENDANCE_BASES:
        raise IncentiveSettingsError("Bonus base must be daily_rate, monthly_basic or fixed.")
    return {
        "bonus_percent": _num(s.get("bonus_percent"), "Bonus %"),
        "base": s["base"],
        "base_amount": _num(s.get("base_amount") or 0, "Base amount"),
        "workdays": _weekdays(s.get("workdays"), "Workdays"),
        "holiday_multiplier": _num(s.get("holiday_multiplier"), "Holiday multiplier", 1),
        "saturday_premium_percent": _num(s.get("saturday_premium_percent"), "Saturday premium %"),
        "leave_counts_as_present": bool(s.get("leave_counts_as_present")),
    }


def parse_applies_to(value) -> list[str]:
    groups = value if isinstance(value, list) else str(value or "").split(",")
    groups = [g.strip() for g in groups if g.strip()]
    if not groups or any(g not in APPLIES_TO for g in groups):
        raise IncentiveSettingsError("Applies to must be drivers and/or helpers.")
    return [g for g in APPLIES_TO if g in groups]


def load_settings(program) -> dict:
    try:
        raw = json.loads(program.settings or "{}")
    except ValueError:
        raw = {}
    try:
        return clean_settings(program.rule_type, raw)
    except IncentiveSettingsError:
        return RULE_TYPES.get(program.rule_type, {}).get("defaults", {})


# --- data --------------------------------------------------------------


def _name(emp: Employee | None) -> str:
    if emp is None:
        return "Unknown"
    return " ".join(p for p in (emp.first_name, emp.last_name, emp.suffix) if p)


def _days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _completed_trips(db: Session, start: date, end: date) -> list[Trip]:
    """COMPLETED, not archived trips that started (PH date) in the period."""
    return (
        db.query(Trip)
        .options(
            joinedload(Trip.trip_helpers),
            joinedload(Trip.trip_rate_profile),
            joinedload(Trip.stops),
        )
        .filter(
            Trip.status == TripStatus.COMPLETED,
            Trip.is_archived.is_(False),
            Trip.start_time >= ph_to_utc(datetime.combine(start, time.min)),
            Trip.start_time < ph_to_utc(datetime.combine(end + timedelta(days=1), time.min)),
        )
        .all()
    )


class _People:
    """Who's who: drivers by user id (Trip.driver_id), helpers by employee
    id (TripHelper.helper_id). Rows are keyed by employee id."""

    def __init__(self, db: Session, groups: list[str]):
        self.groups = groups
        self.users = {}
        self.employees = {}
        self._db = db

    def load(self, user_ids=(), employee_ids=()):
        db = self._db
        if user_ids:
            for u in db.query(User).filter(User.id.in_(set(user_ids))).all():
                self.users[u.id] = u
        emp_ids = set(employee_ids) | {u.employee_id for u in self.users.values() if u.employee_id}
        missing = emp_ids - set(self.employees)
        if missing:
            for e in db.query(Employee).filter(Employee.id.in_(missing)).all():
                self.employees[e.id] = e

    def driver_key(self, user_id):
        u = self.users.get(user_id)
        return u.employee_id if u and u.employee_id else f"u{user_id}"

    def row(self, key, group):
        emp = self.employees.get(key) if isinstance(key, int) else None
        return {
            "employee_id": emp.id if emp else None,
            "name": _name(emp) if emp else f"User #{str(key)[1:]}",
            "department": emp.department if emp else None,
            "group": group,
        }


def _trip_category(trip: Trip) -> str:
    if trip.trip_rate_profile is not None:
        return trip.trip_rate_profile.profile_name or trip.trip_rate_profile.code or ""
    return trip.trip_category or ""


def _is_excluded(trip: Trip, excluded: list[str]) -> bool:
    if not excluded:
        return False
    names = {
        (trip.trip_category or "").lower(),
        (_trip_category(trip) or "").lower(),
        ((trip.trip_rate_profile.code if trip.trip_rate_profile else "") or "").lower(),
    }
    return any(c.lower() in names for c in excluded)


def _ph_start(trip: Trip) -> datetime:
    return utc_to_ph(trip.start_time).replace(tzinfo=None)


# --- rules -------------------------------------------------------------


def _trip_counts(db, program, s, trips):
    """{(key, group): [trip, ...]} for the program's groups."""
    groups = parse_applies_to(program.applies_to)
    people = _People(db, groups)
    people.load(
        user_ids=[t.driver_id for t in trips] if "drivers" in groups else (),
        employee_ids=[h.helper_id for t in trips for h in t.trip_helpers] if "helpers" in groups else (),
    )
    by_person = defaultdict(list)
    for trip in trips:
        if "drivers" in groups:
            by_person[(people.driver_key(trip.driver_id), "driver")].append(trip)
        if "helpers" in groups:
            for h in trip.trip_helpers:
                by_person[(h.helper_id, "helper")].append(trip)
    return people, by_person


def _trip_tiers(db, program, s):
    trips = _completed_trips(db, program.period_start, program.period_end)
    if not s["include_sundays"]:
        trips = [t for t in trips if _ph_start(t).weekday() != 6]
    people, by_person = _trip_counts(db, program, s, trips)
    tiers = s["tiers"]  # highest first
    rows = []
    for (key, group), person_trips in by_person.items():
        count = len({t.id for t in person_trips})
        reached = next((t for t in tiers if count >= t["min_trips"]), None)
        above = [t for t in tiers if count < t["min_trips"]]
        nxt = above[-1] if above else None
        rows.append({
            **people.row(key, group),
            "trips": count,
            "tier": reached["name"] if reached else None,
            "next_tier": nxt["name"] if nxt else None,
            "trips_to_next_tier": nxt["min_trips"] - count if nxt else 0,
            "amount": reached["amount"] if reached else 0,
        })
    return rows


def _daily_cash(db, program, s):
    trips = _completed_trips(db, program.period_start, program.period_end)
    trips = [
        t for t in trips
        if _ph_start(t).weekday() in s["days"] and not _is_excluded(t, s["exclude_categories"])
    ]
    people, by_person = _trip_counts(db, program, s, trips)
    amounts = s["trip_amounts"]
    cutoff = (
        datetime.strptime(s["first_trip_before"], "%H:%M").time()
        if s["first_trip_before"] else None
    )

    def amount_for(n):  # n = 1-based trip of the day
        if n <= len(amounts):
            return amounts[n - 1]
        return amounts[-1] if s["repeat_last"] else 0

    rows = []
    for (key, group), person_trips in by_person.items():
        per_day = defaultdict(list)
        for t in {t.id: t for t in person_trips}.values():
            per_day[_ph_start(t).date()].append(t)
        days = []
        for day in sorted(per_day):
            day_trips = sorted(per_day[day], key=lambda t: t.start_time)
            earned = []
            for n, t in enumerate(day_trips, start=1):
                started = _ph_start(t)
                amt = amount_for(n)
                if n == 1 and cutoff is not None and started.time() >= cutoff:
                    amt = 0
                earned.append({
                    "trip_id": t.id,
                    "ticket_no": t.ticket_no,
                    "started_at": started.strftime("%H:%M"),
                    "nth": n,
                    "amount": amt,
                })
            days.append({
                "date": day.isoformat(),
                "trips": len(day_trips),
                "amount": sum(e["amount"] for e in earned),
                "trip_lines": earned,
            })
        rows.append({
            **people.row(key, group),
            "trips": sum(d["trips"] for d in days),
            "days": days,
            "amount": sum(d["amount"] for d in days),
        })
    return rows


def _km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _default_hub(db) -> Store | None:
    row = db.query(AppSetting).filter(AppSetting.key == "default_hub_store_id").first()
    if row and str(row.value).isdigit():
        return db.query(Store).filter(Store.id == int(row.value)).first()
    return None


def _long_distance(db, program, s):
    trips = _completed_trips(db, program.period_start, program.period_end)
    store_ids = set()
    for t in trips:
        store_ids.update(st.store_id for st in t.stops if st.store_id)
        if t.destination_store_id:
            store_ids.add(t.destination_store_id)
        if t.origin_store_id:
            store_ids.add(t.origin_store_id)
    stores = {st.id: st for st in db.query(Store).filter(Store.id.in_(store_ids)).all()} if store_ids else {}
    hub = _default_hub(db)
    area_km = {a.lower(): km for a, km in s["area_km"].items()}

    def store_km(store, origin):
        if store.area and store.area.strip().lower() in area_km:
            return area_km[store.area.strip().lower()], "area"
        if s["use_gps_distance"] and origin is not None and not store.is_hub:
            return _km(origin.latitude, origin.longitude, store.latitude, store.longitude), "gps"
        return None, None

    def range_for(km):
        for r in reversed(s["ranges"]):
            if km >= r["min_km"] and (r["max_km"] is None or km < r["max_km"]):
                return r
        return None

    people, by_person = _trip_counts(db, program, s, trips)
    trip_info = {}
    for t in trips:
        origin = stores.get(t.origin_store_id) or hub
        ids = {st.store_id for st in t.stops if st.store_id}
        if t.destination_store_id:
            ids.add(t.destination_store_id)
        best = None
        for sid in ids:
            store = stores.get(sid)
            if store is None:
                continue
            km, source = store_km(store, origin)
            if km is not None and (best is None or km > best[0]):
                best = (km, source, store)
        rng = range_for(best[0]) if best else None
        trip_info[t.id] = {
            "trip_id": t.id,
            "ticket_no": t.ticket_no,
            "date": _ph_start(t).date().isoformat(),
            "farthest_store": best[2].name if best else None,
            "area": best[2].area if best else None,
            "km": round(best[0], 1) if best else None,
            "km_source": best[1] if best else None,
            "range": rng["label"] if rng else None,
            "_range": rng,
        }

    rows = []
    for (key, group), person_trips in by_person.items():
        lines = []
        for t in {t.id: t for t in person_trips}.values():
            info = trip_info[t.id]
            rng = info["_range"]
            if rng is None:
                continue
            amt = rng["helper_amount"] + (rng["driver_extra"] if group == "driver" else 0)
            lines.append({k: v for k, v in info.items() if k != "_range"} | {"amount": amt})
        if not lines:
            continue
        lines.sort(key=lambda line: line["date"])
        rows.append({
            **people.row(key, group),
            "trips": len(lines),
            "trip_lines": lines,
            "amount": sum(line["amount"] for line in lines),
        })
    return rows


def _complete_attendance(db, program, s):
    groups = parse_applies_to(program.applies_to)
    roles = [{"drivers": "driver", "helpers": "helper"}[g] for g in groups]
    users = (
        db.query(User)
        .filter(User.role.in_(roles), User.employee_id.isnot(None), User.is_active.is_(True))
        .all()
    )
    role_of = {u.employee_id: (u.role.value if hasattr(u.role, "value") else u.role) for u in users}
    emps = (
        db.query(Employee)
        .filter(Employee.id.in_(role_of.keys()), Employee.is_active == 1)
        .all()
        if role_of else []
    )

    start = program.period_start
    end = min(program.period_end, date.today())
    if end < start:
        return []
    holidays = {
        h.holiday_date: h.holiday_name
        for h in db.query(Holiday).filter(
            Holiday.is_active.is_(True),
            Holiday.holiday_date >= start,
            Holiday.holiday_date <= end,
            Holiday.holiday_type != "special_working",
        )
    }
    emp_ids = [e.id for e in emps]
    present = defaultdict(set)
    if emp_ids:
        for rec in db.query(AttendanceRecord).filter(
            AttendanceRecord.employee_id.in_(emp_ids),
            AttendanceRecord.attendance_date >= start,
            AttendanceRecord.attendance_date <= end,
        ):
            if rec.status in ("Present", "Late") or (rec.status != "Absent" and rec.check_in_time):
                present[rec.employee_id].add(rec.attendance_date)
    on_leave = defaultdict(set)
    if emp_ids:
        for lv in db.query(LeaveRequest).filter(
            LeaveRequest.employee_id.in_(emp_ids),
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= end,
            LeaveRequest.end_date >= start,
        ):
            for d in _days(max(lv.start_date, start), min(lv.end_date, end)):
                on_leave[lv.employee_id].add(d)

    workdays = [d for d in _days(start, end) if d.weekday() in s["workdays"]]
    hol_mult = s["holiday_multiplier"]
    sat_mult = 1 + s["saturday_premium_percent"] / 100
    rows = []
    for emp in emps:
        absences, leave_days = [], 0
        regular = holiday_worked = saturday_worked = 0
        for d in workdays:
            if d in present[emp.id]:
                if d in holidays:
                    holiday_worked += 1
                elif d.weekday() == 5:
                    saturday_worked += 1
                else:
                    regular += 1
            elif d in holidays:
                continue
            elif d in on_leave[emp.id]:
                leave_days += 1
                if not s["leave_counts_as_present"]:
                    absences.append(d.isoformat())
            else:
                absences.append(d.isoformat())
        complete = not absences
        if s["base"] == "daily_rate":
            rate = float(emp.daily_rate or 0)
            base = rate * (regular + holiday_worked * hol_mult + saturday_worked * sat_mult)
        elif s["base"] == "monthly_basic":
            base = float(emp.monthly_basic or 0)
        else:
            base = s["base_amount"]
        group = "driver" if role_of.get(emp.id) == "driver" else "helper"
        rows.append({
            "employee_id": emp.id,
            "name": _name(emp),
            "department": emp.department,
            "group": group,
            "workdays": len(workdays),
            "days_present": regular + holiday_worked + saturday_worked,
            "holidays_worked": holiday_worked,
            "saturdays_worked": saturday_worked,
            "leave_days": leave_days,
            "absences": absences,
            "complete": complete,
            "base": round(base, 2),
            "missing_rate": s["base"] != "fixed" and base == 0,
            "amount": round(base * s["bonus_percent"] / 100, 2) if complete else 0,
        })
    return rows


_COMPUTE = {
    "trip_tiers": _trip_tiers,
    "daily_cash": _daily_cash,
    "long_distance": _long_distance,
    "complete_attendance": _complete_attendance,
}


def compute_program(db: Session, program) -> dict:
    """What everyone earns under `program` (so far, if it's still
    running). Rows sorted by amount, then name."""
    s = load_settings(program)
    rows = _COMPUTE[program.rule_type](db, program, s)
    rows.sort(key=lambda r: (-r["amount"], r["name"]))
    return {
        "program_id": program.id,
        "rule_type": program.rule_type,
        "period_start": program.period_start.isoformat(),
        "period_end": program.period_end.isoformat(),
        "is_final": date.today() > program.period_end,
        "rows": rows,
        "earners": sum(1 for r in rows if r["amount"] > 0),
        "total": round(sum(r["amount"] for r in rows), 2),
    }
