"""Which driver/helper rate a trip pays.

Rules (tpc_trip_rate_rules) match a trip on any of: trip category, truck
type, lane (origin store + destination area). Blank fields match
anything. For each rate, the most specific matching rule in effect on
the trip date wins (ties: the latest effective date); a rule that leaves
a rate blank passes it down to the next rule, and finally to the trip
category's own rate.

Example: category "Core no helpers" pays 565. A rule "Core no helpers +
Wingvan = 1,000" makes a wingvan trip pay 1,000, and a rule "Core no
helpers from Oct 14 = 602" raises every other truck from Oct 14 on.

Driver 1st is three parts: driver_first_trip_rate (basic), driver_allowance
and driver_other, each stored and overridden on its own -- a rule changing
only the basic keeps the allowance. Once resolved, driver_first_trip_rate is
the TOTAL a first trip pays (what payroll and the driver app read), with the
parts in driver_basic_rate / driver_allowance / driver_other.

Driver Next, Helper 1st and Helper Next work the same way with one "other"
part each (driver_next_other, helper_first_other, helper_next_other): once
resolved, the rate is the total and its basic is in driver_next_basic_rate /
helper_first_basic_rate / helper_next_basic_rate.

A 2-helper category can also have 1-helper rates (one_helper_*: Helper 1st /
Next, each with an other), paid when the trip has only 1 helper. Blank =
the normal helper rates. On such a trip the helper_* keys hold the 1-helper
rates and helper_rate_note says so.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models.trip_rate_rule import TripRateRule

RATE_FIELDS = (
    "driver_first_trip_rate",
    "driver_allowance",
    "driver_other",
    "driver_next_trip_rate",
    "helper_first_trip_rate",
    "helper_next_trip_rate",
    "driver_next_other",
    "helper_first_other",
    "helper_next_other",
    "one_helper_first_trip_rate",
    "one_helper_first_other",
    "one_helper_next_trip_rate",
    "one_helper_next_other",
)

# Blank on the category means "not set" (use the normal helper rates), so
# these stay None instead of 0.
ONE_HELPER_FIELDS = (
    "one_helper_first_trip_rate",
    "one_helper_first_other",
    "one_helper_next_trip_rate",
    "one_helper_next_other",
)
_OPTIONAL_FIELDS = set(ONE_HELPER_FIELDS)

# rate -> (its other part, where its basic goes once resolved).
_OTHER_PARTS = {
    "driver_next_trip_rate": ("driver_next_other", "driver_next_basic_rate"),
    "helper_first_trip_rate": ("helper_first_other", "helper_first_basic_rate"),
    "helper_next_trip_rate": ("helper_next_other", "helper_next_basic_rate"),
    "one_helper_first_trip_rate": ("one_helper_first_other", "one_helper_first_basic_rate"),
    "one_helper_next_trip_rate": ("one_helper_next_other", "one_helper_next_basic_rate"),
}

# Helper rate -> its 1-helper version (rate, other, basic).
_ONE_HELPER = {
    "helper_first": "one_helper_first",
    "helper_next": "one_helper_next",
}


def _base_rates(profile) -> dict:
    """A category's stored rates (0 when there's no category)."""
    rates = {}
    for field in RATE_FIELDS:
        value = getattr(profile, field, None) if profile else None
        if field in _OPTIONAL_FIELDS:
            rates[field] = float(value) if value is not None else None
        else:
            rates[field] = float(value or 0)
    return rates


def _helper_count(trip) -> int:
    helpers = getattr(trip, "trip_helpers", None)
    return len(helpers) if helpers is not None else 0

# How much each matched field counts towards "more specific".
_WEIGHTS = {
    "trip_rate_profile_id": 1,
    "truck_type_id": 2,
    "origin_store_id": 4,
    "destination_area": 4,
    # One exact outlet beats an area.
    "destination_store_id": 6,
}


def load_rules(db: Session) -> list[TripRateRule]:
    return db.query(TripRateRule).all()


def _norm(value):
    return (value or "").strip().lower() or None


def trip_facts(trip) -> dict:
    """What a rule can match on, read from a trip (with its vehicle,
    category and destination store loaded or lazy-loadable)."""
    vehicle = getattr(trip, "vehicle_unit", None)
    destination = getattr(trip, "destination_store", None)
    return {
        "trip_rate_profile_id": trip.trip_rate_profile_id,
        "truck_type_id": vehicle.truck_type_id if vehicle else None,
        "origin_store_id": trip.origin_store_id,
        "destination_area": _norm(destination.area) if destination else None,
        "destination_store_id": trip.destination_store_id,
    }


def _matches(rule: TripRateRule, facts: dict, on: date | None) -> int | None:
    """Specificity score when the rule applies, else None."""
    if on is not None and rule.effective_from and rule.effective_from > on:
        return None
    score = 0
    for field, weight in _WEIGHTS.items():
        wanted = getattr(rule, field)
        if field == "destination_area":
            wanted = _norm(wanted)
        if wanted is None:
            continue
        if facts.get(field) != wanted:
            return None
        score += weight
    return score


def describe_rule(rule: TripRateRule) -> str:
    parts = []
    if rule.trip_rate_profile:
        parts.append(rule.trip_rate_profile.profile_name)
    if rule.truck_type:
        parts.append(rule.truck_type.name)
    if rule.origin_store_id or rule.destination_area or rule.destination_store_id:
        origin = rule.origin_store.name if rule.origin_store else "Any"
        to = (
            rule.destination_store.name
            if rule.destination_store
            else rule.destination_area or "Any"
        )
        parts.append(f"{origin} → {to}")
    label = " · ".join(parts) or "All trips"
    return f"{label} (from {rule.effective_from:%b %d, %Y})"


def _with_first_total(rates: dict) -> dict:
    """The stored basics move to *_basic_rate; each rate becomes what that
    trip pays (driver_first_trip_rate: basic + allowance + other; the rest:
    basic + other)."""
    basic = rates["driver_first_trip_rate"]
    totals = {
        "driver_basic_rate": basic,
        "driver_first_trip_rate": round(basic + rates["driver_allowance"] + rates["driver_other"], 2),
    }
    for field, (other, basic_key) in _OTHER_PARTS.items():
        totals[basic_key] = rates[field]
        # A 1-helper rate not set stays None (the normal rate is paid).
        totals[field] = (
            None if rates[field] is None else round(rates[field] + (rates[other] or 0), 2)
        )
    return {**rates, **totals}


def _apply_one_helper(rates: dict) -> dict:
    """The trip has 1 helper on a 2-helper category: each helper rate with
    a 1-helper version set pays that instead."""
    used = False
    for normal, one in _ONE_HELPER.items():
        if rates[f"{one}_trip_rate"] is None:
            continue
        rates[f"{normal}_trip_rate"] = rates[f"{one}_trip_rate"]
        rates[f"{normal}_basic_rate"] = rates[f"{one}_basic_rate"]
        rates[f"{normal}_other"] = rates[f"{one}_other"] or 0.0
        used = True
    if used:
        rates["helper_rate_note"] = "1-helper rate"
    return rates


def resolve_trip_rates(trip, on: date | None, rules: list[TripRateRule]) -> dict:
    """The four rates for this trip on `on` (its PH trip date), plus a
    short label of where the driver rate came from."""
    profile = trip.trip_rate_profile
    rates = _base_rates(profile)
    source = profile.profile_name if profile else None

    facts = trip_facts(trip)
    ranked = sorted(
        (
            (score, rule)
            for rule in rules
            if (score := _matches(rule, facts, on)) is not None
        ),
        key=lambda pair: (pair[0], pair[1].effective_from, pair[1].id),
        reverse=True,
    )
    for field in RATE_FIELDS:
        for _, rule in ranked:
            value = getattr(rule, field)
            if value is not None:
                rates[field] = float(value)
                if field == "driver_first_trip_rate":
                    source = describe_rule(rule)
                break

    resolved = {**_with_first_total(rates), "rate_source": source}
    if profile and (getattr(profile, "helper_count", 0) or 0) >= 2 and _helper_count(trip) == 1:
        resolved = _apply_one_helper(resolved)
    return resolved


def _is_category_only(rule: TripRateRule) -> bool:
    return not (
        rule.truck_type_id
        or rule.origin_store_id
        or rule.destination_area
        or rule.destination_store_id
    )


def category_rates(profile, rules: list[TripRateRule], on: date) -> dict:
    """A category's own rates on a date (no truck / lane): its base rates
    with the dated changes in effect then. For the Trip Categories cards."""
    facts = {
        "trip_rate_profile_id": profile.id,
        "truck_type_id": None,
        "origin_store_id": None,
        "destination_area": None,
        "destination_store_id": None,
    }
    rates = _base_rates(profile)
    since = None
    ranked = sorted(
        (
            (score, rule)
            for rule in rules
            if (score := _matches(rule, facts, on)) is not None
        ),
        key=lambda pair: (pair[0], pair[1].effective_from, pair[1].id),
        reverse=True,
    )
    for field in RATE_FIELDS:
        for _, rule in ranked:
            value = getattr(rule, field)
            if value is not None:
                rates[field] = float(value)
                since = max(since, rule.effective_from) if since else rule.effective_from
                break
    return {**_with_first_total(rates), "since": since.isoformat() if since else None}


def category_rate_changes(profile, rules: list[TripRateRule]) -> list[dict]:
    """This category's dated rate changes (category-only rules), newest
    first -- the ones set from the category card."""
    changes = [
        rule
        for rule in rules
        if rule.trip_rate_profile_id == profile.id and _is_category_only(rule)
    ]
    changes.sort(key=lambda r: r.effective_from, reverse=True)
    return [
        {
            "id": rule.id,
            "effective_from": rule.effective_from.isoformat(),
            **{
                field: float(getattr(rule, field)) if getattr(rule, field) is not None else None
                for field in RATE_FIELDS
            },
            "notes": rule.notes,
        }
        for rule in changes
    ]
