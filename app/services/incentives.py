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
#                          in the store's name, address or area; a start
#                          yard not on the list uses the default hub's
#                          rows), else from the straight-line km from the
#                          trip's origin / the default hub. A store at
#                          0,0 has no location (no km). The trip's
#                          farthest (highest level) stop counts -- each
#                          stop measured from the hub, never added up.
#   complete_attendance -- every workday present (approved leave and
#                          holidays don't break it); bonus % of the
#                          base, weekday holidays worked x2, Saturdays
#                          +30% when the base is the daily rate.
# A trip's day is the PH date it started (same as payroll / route rides).
#
#
# Paying out is separate from payroll: an Incentive Run
# (app/services/incentive_runs.py) computes programs for a period with
# their settings frozen, then goes Draft -> Approved -> Released (cash,
# with payroll as a separate line after net pay, or bank).

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
            "hubs": [],
            "origin_store_id": None,
            "origin": None,
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


# How a run of each type is usually paid out (the New Run form's
# default): the memos' tiers / daily cash are cash; the rest with payroll.
RELEASE_METHODS = ("cash", "payroll", "bank")
DEFAULT_RELEASE_METHOD = {
    "trip_tiers": "cash",
    "daily_cash": "cash",
    "long_distance": "payroll",
    "complete_attendance": "payroll",
}


def clean_settings(rule_type: str, settings: dict | None) -> dict:
    """The type's defaults with `settings` laid over, checked. Raises
    IncentiveSettingsError with a message for the page."""
    if rule_type not in RULE_TYPES:
        raise IncentiveSettingsError("Unknown incentive type.")
    settings = {k: v for k, v in (settings or {}).items() if k != "pay_in_payroll"}
    return _clean_type(rule_type, settings)


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
            # Only these hubs' drivers / helpers (by department); empty = all.
            "hubs": [h for h in HUB_DEPARTMENTS if h in (s.get("hubs") or [])],
            # Only trips starting from this hub (store id); None = any.
            "origin_store_id": (
                None if s.get("origin_store_id") in (None, "") else int(s["origin_store_id"])
            ),
            "origin": str(s.get("origin") or "").strip()[:100] or None,
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


# Daily cash "hubs": which departments each hub's drivers / helpers are in
# (same pairs as trip helper matching, app/api/driver/trips.py).
HUB_DEPARTMENTS = {
    "cdc": {"label": "Coca-Cola hub", "driver": "CdcDriver", "helper": "CdcHelper"},
    "cpdc": {"label": "Consolacion hub", "driver": "CpdcDriver", "helper": "CpdcHelper"},
}


def _daily_cash(db, program, s):
    trips = _completed_trips(db, program.period_start, program.period_end)
    trips = [
        t for t in trips
        if _ph_start(t).weekday() in s["days"] and not _is_excluded(t, s["exclude_categories"])
        # Origin picked: only trips starting from that hub (they're also
        # the only ones numbered 1st / 2nd... for the day).
        and (not s.get("origin_store_id") or t.origin_store_id == s["origin_store_id"])
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

    # Only the picked hubs' people (their department); none picked = all.
    allowed = {
        HUB_DEPARTMENTS[h][role] for h in s.get("hubs") or [] for role in ("driver", "helper")
    }

    rows = []
    for (key, group), person_trips in by_person.items():
        if allowed and people.row(key, group)["department"] not in allowed:
            continue
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


# Why a stop / trip earns no long-distance level (Preview -> Trip check).
# In this order: a trip with several zero stops shows the first one here,
# so something fixable comes before "too near".
LD_REASONS = {
    "gps_off": "City not on the route list, and GPS distance is off",
    "store_no_location": "Store has no location (0,0) and its city isn't on the route list",
    "origin_no_location": "Start hub has no location (0,0)",
    "no_origin": "No start hub (trip has no origin and no default hub is set)",
    "within_free_km": "Within the free distance",
    "hub": "Stop is a hub",
    "no_stops": "No stores on the trip",
}


def has_location(store) -> bool:
    """False for a store saved at 0,0 (how "no location" ends up stored).
    Measuring from / to 0,0 would put it ~13,700 km away (top level)."""
    if store is None or store.latitude is None or store.longitude is None:
        return False
    return not (abs(store.latitude) < 0.0001 and abs(store.longitude) < 0.0001)


def store_text(store) -> str:
    """Name + address + area as whole words, for finding a route city
    ("Promo SH Carcar City" -> carcar). Hyphens joined too, so "Car-Car"
    also reads "carcar"."""
    raw = f"{store.name or ''} {store.address or ''} {store.area or ''}"
    return _words(raw) + _words(raw.replace("-", ""))


class LongDistance:
    """Levels for one long-distance program: per store (route list first,
    then the straight-line km from the trip's start hub) and per trip (its
    farthest stop). Shared by the program, Preview's Trip check and the
    Store check."""

    def __init__(self, db: Session, s: dict):
        self.db = db
        self.s = s
        self.hub = _default_hub(db)
        # Route list rows: (start hub store id or None = any hub, city,
        # its spellings, level).
        self.routes = [
            (r["origin_store_id"], city, _city_variants(city), r["level"])
            for r in s["routes"]
            for city in r["cities"]
        ]
        self.route_hubs = {oid for oid, *_ in self.routes if oid}

    def cap(self, level):
        level = max(level, 0)
        return min(level, self.s["max_steps"]) if self.s["max_steps"] else level

    def route_match(self, store, origin_id):
        """(level, city) from the route list, or None. The trip's own
        hub's rows win over any-hub rows. A start point that isn't on the
        route list (another yard) uses the default hub's rows."""
        text = store_text(store)
        if origin_id not in self.route_hubs and self.hub is not None:
            origin_id = self.hub.id
        for wanted in ((origin_id,) if origin_id else ()) + (None,):
            hits = [
                (level, city)
                for oid, city, variants, level in self.routes
                if oid == wanted and any(v in text for v in variants)
            ]
            if hits:
                level, city = max(hits)
                return self.cap(level), city
        return None

    def store_level(self, store, origin) -> dict:
        """{level, km, source ("route" / "gps" / None), city, reason}."""
        out = {"level": 0, "km": None, "source": None, "city": None, "reason": None}
        hit = self.route_match(store, origin.id if origin else None)
        if hit:
            out.update(level=hit[0], source="route", city=hit[1])
            return out
        if store.is_hub:
            out["reason"] = "hub"
        elif not self.s["use_gps_distance"]:
            out["reason"] = "gps_off"
        elif origin is None:
            out["reason"] = "no_origin"
        elif not has_location(origin):
            out["reason"] = "origin_no_location"
        elif not has_location(store):
            out["reason"] = "store_no_location"
        else:
            km = _km(origin.latitude, origin.longitude, store.latitude, store.longitude)
            free, step = self.s["free_km"], self.s["step_km"]
            # The first `free` km earn nothing; each started `step` after
            # it is a level (31-60 km = 1 with 30 free and 30 km steps).
            level = self.cap(math.ceil((km - free) / step) if km > free else 0)
            out.update(level=level, km=km, source="gps")
            if not level:
                out["reason"] = "within_free_km"
        return out

    def load_stores(self, trips):
        ids = set()
        for t in trips:
            ids.update(st.store_id for st in t.stops if st.store_id)
            if t.destination_store_id:
                ids.add(t.destination_store_id)
            if t.origin_store_id:
                ids.add(t.origin_store_id)
        return {st.id: st for st in self.db.query(Store).filter(Store.id.in_(ids)).all()} if ids else {}

    def trip_info(self, t, stores) -> dict:
        origin = stores.get(t.origin_store_id) or self.hub
        ids = [st.store_id for st in sorted(t.stops, key=lambda x: x.id) if st.store_id]
        if t.destination_store_id and t.destination_store_id not in ids:
            ids.append(t.destination_store_id)
        stops, best = [], None
        for sid in ids:
            store = stores.get(sid)
            if store is None:
                continue
            info = self.store_level(store, origin)
            stops.append({"store_id": store.id, "name": store.name} | info)
            if info["level"] and (best is None or info["level"] > best["level"]):
                best = stops[-1]
        reason = None
        if not best:
            reasons = [x["reason"] for x in stops if x["reason"]]
            reason = "no_stops" if not stops else (
                # The most telling one: a fixable setting before "too near".
                next((r for r in LD_REASONS if r in reasons), None)
            )
        return {
            "trip_id": t.id,
            "ticket_no": t.ticket_no,
            "date": _ph_start(t).date().isoformat(),
            "origin": origin.name if origin else None,
            "farthest_store": best["name"] if best else None,
            "city": best["city"] if best else None,
            "level": best["level"] if best else 0,
            "km": round(best["km"], 1) if best and best["km"] is not None else None,
            "level_source": best["source"] if best else None,
            "reason": reason,
            "stops": [
                x | {"km": round(x["km"], 1) if x["km"] is not None else None} for x in stops
            ],
        }


def _long_distance(db, program, s):
    trips = _completed_trips(db, program.period_start, program.period_end)
    ld = LongDistance(db, s)
    stores = ld.load_stores(trips)
    trip_info = {t.id: ld.trip_info(t, stores) for t in trips}

    people, by_person = _trip_counts(db, program, s, trips)
    rows = []
    for (key, group), person_trips in by_person.items():
        lines = []
        for t in {t.id: t for t in person_trips}.values():
            info = trip_info[t.id]
            if not info["level"]:
                continue
            per = s["driver_per_step"] if group == "driver" else s["helper_per_step"]
            line = {k: v for k, v in info.items() if k not in ("stops", "reason")}
            lines.append(line | {"amount": info["level"] * per})
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


def long_distance_trip_check(db: Session, program, s: dict) -> dict:
    """Every trip in the program's period with its level -- including the
    ones that earn nothing and why -- plus the trips not completed yet."""
    start, end = program.period_start, program.period_end
    trips = _completed_trips(db, start, end)
    ld = LongDistance(db, s)
    stores = ld.load_stores(trips)
    groups = parse_applies_to(program.applies_to)
    people = _People(db, groups)
    people.load(
        user_ids=[t.driver_id for t in trips],
        employee_ids=[h.helper_id for t in trips for h in t.trip_helpers],
    )
    rows = []
    for t in sorted(trips, key=lambda x: (x.start_time, x.id)):
        info = ld.trip_info(t, stores)
        key = people.driver_key(t.driver_id)
        driver = people.row(key, "driver")
        info["driver"] = driver["name"]
        info["driver_linked"] = driver["employee_id"] is not None
        info["helpers"] = [people.row(h.helper_id, "helper")["name"] for h in t.trip_helpers]
        info["driver_amount"] = info["level"] * s["driver_per_step"] if "drivers" in groups else 0
        info["helper_amount"] = info["level"] * s["helper_per_step"] if "helpers" in groups else 0
        rows.append(info)

    # Trips in the period still on their way to Completed (they don't
    # count yet).
    lo = ph_to_utc(datetime.combine(start, time.min))
    hi = ph_to_utc(datetime.combine(end + timedelta(days=1), time.min))
    from sqlalchemy import func as _func

    waiting = dict(
        db.query(Trip.status, _func.count(Trip.id))
        .filter(
            Trip.is_archived.is_(False),
            Trip.start_time >= lo,
            Trip.start_time < hi,
            Trip.status.notin_([TripStatus.COMPLETED, TripStatus.CANCELLED]),
        )
        .group_by(Trip.status)
        .all()
    )
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "applies_to": groups,
        "use_gps_distance": bool(s["use_gps_distance"]),
        "route_count": len(s["routes"]),
        "free_km": s["free_km"],
        "default_hub": ld.hub.name if ld.hub else None,
        "trips": rows,
        "waiting": {
            (k.value if hasattr(k, "value") else str(k)): v for k, v in waiting.items()
        },
        "reasons": LD_REASONS,
    }


def long_distance_store_check(db: Session, program, s: dict) -> dict:
    """Every store with what long distance can do with it: its route city
    (and level from the default hub), whether it has a location, and how
    many trips in the program's period visit it."""
    from sqlalchemy import func as _func

    from app.models.trip_stops import TripStop

    ld = LongDistance(db, s)
    lo = ph_to_utc(datetime.combine(program.period_start, time.min))
    hi = ph_to_utc(datetime.combine(program.period_end + timedelta(days=1), time.min))
    in_period = (
        Trip.is_archived.is_(False),
        Trip.status != TripStatus.CANCELLED,
        Trip.start_time >= lo,
        Trip.start_time < hi,
    )
    visits = defaultdict(set)
    for store_id, trip_id in (
        db.query(TripStop.store_id, TripStop.trip_id)
        .join(Trip, Trip.id == TripStop.trip_id)
        .filter(TripStop.store_id.isnot(None), *in_period)
    ):
        visits[store_id].add(trip_id)
    for store_id, trip_id in db.query(Trip.destination_store_id, Trip.id).filter(
        Trip.destination_store_id.isnot(None), *in_period
    ):
        visits[store_id].add(trip_id)

    hub = ld.hub
    rows = []
    for store in db.query(Store).order_by(Store.name).all():
        located = has_location(store)
        if store.is_hub:
            status = "ok" if located else "hub_no_location"
            city = level = km = None
        else:
            hit = ld.route_match(store, hub.id if hub else None)
            city, level = (hit[1], hit[0]) if hit else (None, None)
            km = None
            if located and hub is not None and has_location(hub):
                km = round(_km(hub.latitude, hub.longitude, store.latitude, store.longitude), 1)
            if hit:
                status = "ok" if located else "route_no_location"
            elif located:
                status = "gps_only"
            else:
                status = "no_city_no_location"
        rows.append({
            "id": store.id,
            "name": store.name,
            "address": store.address,
            "area": store.area,
            "is_hub": bool(store.is_hub),
            "has_location": located,
            "city": city,
            "level": level,
            "km_from_hub": km,
            "trips": len(visits.get(store.id, ())),
            "status": status,
        })
    return {
        "default_hub": hub.name if hub else None,
        "default_hub_has_location": has_location(hub) if hub else False,
        "use_gps_distance": bool(s["use_gps_distance"]),
        "stores": rows,
    }


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


def compute_program(
    db: Session,
    program,
    start: date | None = None,
    end: date | None = None,
    settings: dict | None = None,
) -> dict:
    """What everyone earns under `program` (so far, if it's still
    running). Rows sorted by amount, then name. `start` / `end` narrow
    the period (a run's period); `settings` overrides the program's (an
    incentive run's frozen copy)."""
    s = settings if settings is not None else load_settings(program)
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
    """A program seen through part of its period (a run's period)."""

    def __init__(self, program, start, end):
        self._program = program
        self.period_start = max(program.period_start, start or program.period_start)
        self.period_end = min(program.period_end, end or program.period_end)

    def __getattr__(self, name):
        return getattr(self._program, name)
