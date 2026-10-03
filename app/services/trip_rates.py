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
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models.trip_rate_rule import TripRateRule

RATE_FIELDS = (
    "driver_first_trip_rate",
    "driver_next_trip_rate",
    "helper_first_trip_rate",
    "helper_next_trip_rate",
)

# How much each matched field counts towards "more specific".
_WEIGHTS = {
    "trip_rate_profile_id": 1,
    "truck_type_id": 2,
    "origin_store_id": 4,
    "destination_area": 4,
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
    if rule.origin_store_id or rule.destination_area:
        origin = rule.origin_store.name if rule.origin_store else "Any"
        parts.append(f"{origin} → {rule.destination_area or 'Any'}")
    label = " · ".join(parts) or "All trips"
    return f"{label} (from {rule.effective_from:%b %d, %Y})"


def resolve_trip_rates(trip, on: date | None, rules: list[TripRateRule]) -> dict:
    """The four rates for this trip on `on` (its PH trip date), plus a
    short label of where the driver rate came from."""
    profile = trip.trip_rate_profile
    rates = {
        field: float(getattr(profile, field) or 0) if profile else 0.0
        for field in RATE_FIELDS
    }
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

    return {**rates, "rate_source": source}
