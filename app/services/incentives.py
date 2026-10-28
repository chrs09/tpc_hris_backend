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
#   long_distance       -- a level per 30 km past the first 30 (31-60 km
#                          = 1, 61-90 = 2 ... capped at max_steps); the
#                          driver gets 50 and the helper 20 per level. The
#                          level comes from the route list (start hub +
#                          destination city, e.g. Consolacion -> Sogod =
#                          1, Cebu Plant -> Carcar = 1; the city is found
#                          in the store's address), else from the
#                          straight-line km from the trip's origin / the
#                          default hub. The trip's farthest (highest
#                          level) destination counts.
#   complete_attendance -- every workday present (approved leave and
#                          holidays don't break it); bonus % of the
#                          base, weekday holidays worked x2, Saturdays
#                          +30% when the base is the daily rate.
# A trip's day is the PH date it started (same as payroll / route rides).
#
# pay_in_payroll (every type): the amount goes in the Payroll page's
# Incentives column (and gross pay). Per-trip types (long distance, daily
# cash) count the trips inside the cutoff; whole-period types (tiers,
# attendance) are paid in the cutoff their release date (else period end)
# falls in. Off by default for daily cash (the coordinator pays it in
# cash) and tiers (released in cash on the 5th per the memos).

import json
import math
import re
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
            "free_km": 30,
            "step_km": 30,
            "driver_per_step": 50,
            "helper_per_step": 20,
            "max_steps": 4,
            "routes": [],
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


PAY_IN_PAYROLL_DEFAULT = {
    "trip_tiers": False,
    "daily_cash": False,
    "long_distance": True,
    "complete_attendance": True,
}
PER_TRIP_TYPES = ("daily_cash", "long_distance")


def clean_settings(rule_type: str, settings: dict | None) -> dict:
    """The type's defaults with `settings` laid over, checked. Raises
    IncentiveSettingsError with a message for the page."""
    if rule_type not in RULE_TYPES:
        raise IncentiveSettingsError("Unknown incentive type.")
    settings = settings or {}
    pay = settings.get("pay_in_payroll")
    cleaned = _clean_type(rule_type, settings)
    cleaned["pay_in_payroll"] = PAY_IN_PAYROLL_DEFAULT[rule_type] if pay is None else bool(pay)
    return cleaned


def _clean_type(rule_type: str, settings: dict) -> dict:
    s = {**RULE_TYPES[rule_type]["defaults"], **settings}

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
        max_steps = s.get("max_steps")
        max_steps = None if max_steps in (None, "") else int(_num(max_steps, "Max level", 1))
        routes = []
        for i, r in enumerate(s.get("routes") or [], start=1):
            cities = r.get("cities") or []
            if isinstance(cities, str):
                cities = cities.split("/")
            cities = [str(c).strip() for c in cities if str(c).strip()]
            if not cities:
                raise IncentiveSettingsError(f"Route {i}: add at least one destination city.")
            origin_id = r.get("origin_store_id")
            routes.append({
                "origin_store_id": None if origin_id in (None, "") else int(origin_id),
                "origin": str(r.get("origin") or "").strip()[:100] or None,
                "cities": cities,
                "level": int(_num(r.get("level"), f"Route {i} level")),
                "direction": str(r.get("direction") or "").strip()[:30] or None,
            })
        return {
            "free_km": _num(s.get("free_km") or 0, "Km before the first level"),
            "step_km": _num(s.get("step_km"), "Km per level", 1),
            "driver_per_step": _num(s.get("driver_per_step"), "Driver amount per level"),
            "helper_per_step": _num(s.get("helper_per_step"), "Helper amount per level"),
            "max_steps": max_steps,
            "routes": routes,
            "use_gps_distance": bool(s.get("use_gps_distance")),
        }

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
        return clean_settings(program.rule_type, {})


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


def _words(text: str) -> str:
    """Lower-case words with single spaces around them ("Car-Car City,
    Cebu" -> " car car city cebu "), for whole-word matching."""
    return f" {' '.join(re.findall(r'[a-z0-9]+', (text or '').lower()))} "


def _city_variants(city: str) -> list[str]:
    """" car car " and " carcar " -- the sheet and addresses spell cities
    both ways."""
    spaced = _words(city)
    return [spaced, f" {spaced.replace(' ', '')} "] if spaced.strip() else []


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
    step, free = s["step_km"], s["free_km"]

    def cap(level):
        level = max(level, 0)
        return min(level, s["max_steps"]) if s["max_steps"] else level

    # Route list rows: (origin store id or None = any hub, city, its
    # spellings, level).
    routes = [
        (r["origin_store_id"], city, _city_variants(city), r["level"])
        for r in s["routes"]
        for city in r["cities"]
    ]

    def store_level(store, origin):
        """(level, km or None, source, city) for one destination. The city
        is looked up in the store's address (then its area); the trip's
        own hub's rows win over any-hub rows."""
        raw = f"{store.address or ''} {store.area or ''}"
        # Also with hyphens joined, so "Car-Car" matches "Carcar".
        text = _words(raw) + _words(raw.replace("-", ""))
        origin_id = origin.id if origin else None
        for wanted in ((origin_id,) if origin_id else ()) + (None,):
            hits = [
                (level, city)
                for oid, city, variants, level in routes
                if oid == wanted and any(v in text for v in variants)
            ]
            if hits:
                level, city = max(hits)
                return cap(level), None, "route", city
        if s["use_gps_distance"] and origin is not None and not store.is_hub:
            km = _km(origin.latitude, origin.longitude, store.latitude, store.longitude)
            # The first `free` km earn nothing; each started `step` after
            # it is a level (31-60 km = 1 with 30 free and 30 km steps).
            return cap(math.ceil((km - free) / step) if km > free else 0), km, "gps", None
        return None, None, None, None

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
            level, km, source, city = store_level(store, origin)
            if level is not None and (best is None or level > best[0]):
                best = (level, km, source, store, city)
        trip_info[t.id] = {
            "trip_id": t.id,
            "ticket_no": t.ticket_no,
            "date": _ph_start(t).date().isoformat(),
            "origin": origin.name if origin else None,
            "farthest_store": best[3].name if best else None,
            "city": best[4] if best else None,
            "level": best[0] if best else 0,
            "km": round(best[1], 1) if best and best[1] is not None else None,
            "level_source": best[2] if best else None,
        }

    rows = []
    for (key, group), person_trips in by_person.items():
        lines = []
        for t in {t.id: t for t in person_trips}.values():
            info = trip_info[t.id]
            if not info["level"]:
                continue
            per = s["driver_per_step"] if group == "driver" else s["helper_per_step"]
            lines.append(info | {"amount": info["level"] * per})
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


def compute_program(db: Session, program, start: date | None = None, end: date | None = None) -> dict:
    """What everyone earns under `program` (so far, if it's still
    running). Rows sorted by amount, then name. `start` / `end` narrow
    the period (a payroll cutoff)."""
    s = load_settings(program)
    if start or end:
        program = _Window(program, start, end)
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


class _Window:
    """A program seen through part of its period (a payroll cutoff)."""

    def __init__(self, program, start, end):
        self._program = program
        self.period_start = max(program.period_start, start or program.period_start)
        self.period_end = min(program.period_end, end or program.period_end)

    def __getattr__(self, name):
        return getattr(self._program, name)


def payroll_incentives(db: Session, start: date, end: date) -> dict:
    """{employee_id: {"total", "lines": [{program_id, name, rule_type,
    amount}]}} -- incentives paid through payroll for the cutoff
    start..end (see pay_in_payroll above)."""
    from app.models.incentive_program import IncentiveProgram

    programs = (
        db.query(IncentiveProgram)
        .filter(IncentiveProgram.is_active.is_(True))
        .order_by(IncentiveProgram.period_start, IncentiveProgram.id)
        .all()
    )
    result = {}
    for program in programs:
        if program.rule_type not in _COMPUTE:
            continue
        s = load_settings(program)
        if not s.get("pay_in_payroll"):
            continue
        if program.rule_type in PER_TRIP_TYPES:
            if program.period_start > end or program.period_end < start:
                continue
            computed = compute_program(db, program, start, end)
        else:
            pay_day = program.release_date or program.period_end
            if not (start <= pay_day <= end):
                continue
            computed = compute_program(db, program)
        for row in computed["rows"]:
            if not row.get("employee_id") or not row["amount"]:
                continue
            entry = result.setdefault(row["employee_id"], {"total": 0, "lines": []})
            entry["lines"].append({
                "program_id": program.id,
                "name": program.name,
                "rule_type": program.rule_type,
                "amount": row["amount"],
            })
            entry["total"] = round(entry["total"] + row["amount"], 2)
    return result
