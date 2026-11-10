"""Customer Chart rules for a trip (Trip Dispatch, Edit Assigned Trip,
Trip Manual Entries, rate preview).

A trip belongs to the customer and tier of its FIRST destination (every
location sits under one tier of one customer). The tier decides the rate:

  rate_source "lane"          -- a Driver Rates lane rule (truck type +
                                 origin -> location). No lane rule: the
                                 location's trip profile. Neither: blocked.
  rate_source "trip_profile"  -- the location's trip profile (a more
                                 specific Driver Rates rule still
                                 overrides it, as before). None: blocked.

A location not on the chart yet ("Unassigned") works as before: its trip
profile, required. All destinations of one trip must be the same customer.
"""

import json
from datetime import date
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.customer import RATE_SOURCE_LANE, CustomerTier
from app.models.TripRate import TripRateProfile
from app.services.trip_rates import lane_rule_for, load_rules, resolve_trip_rates


def tier_truck_type_ids(tier: CustomerTier | None) -> list[int]:
    if not tier or not tier.truck_type_ids:
        return []
    try:
        return [int(x) for x in json.loads(tier.truck_type_ids)]
    except (TypeError, ValueError):
        return []


def _active_profile(db: Session, store) -> TripRateProfile | None:
    if not store.trip_rate_profile_id:
        return None
    return (
        db.query(TripRateProfile)
        .filter(
            TripRateProfile.id == store.trip_rate_profile_id,
            TripRateProfile.is_active.is_(True),
        )
        .first()
    )


def plan_trip(
    db: Session,
    destinations: list,
    origin,
    vehicle,
    on: date | None,
    rules=None,
    expected_tier_id: int | None = None,
) -> SimpleNamespace:
    """-> SimpleNamespace(profile, tier, customer_id, lane_rule).
    Raises HTTPException(400) saying what to fix when the trip can't go."""
    primary = destinations[0]
    tier = primary.customer_tier if primary.customer_tier_id else None
    if tier is not None and not tier.is_active:
        raise HTTPException(
            status_code=400,
            detail=f'"{primary.name}" is under tier {tier.name}, which is turned off on the Customer Chart.',
        )
    if expected_tier_id and (tier is None or tier.id != int(expected_tier_id)):
        raise HTTPException(
            status_code=400,
            detail=f'"{primary.name}" isn\'t in the tier picked for this trip.',
        )

    if tier is not None:
        for store in destinations[1:]:
            other = store.customer_tier if store.customer_tier_id else None
            if other is None or other.customer_id != tier.customer_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f'"{store.name}" isn\'t under {tier.customer.name}. '
                        "All stops of one trip must be for the same customer."
                    ),
                )
        allowed = tier_truck_type_ids(tier)
        if allowed and (not vehicle or vehicle.truck_type_id not in allowed):
            raise HTTPException(
                status_code=400,
                detail=f"Tier {tier.name} of {tier.customer.name} doesn't allow this truck type.",
            )

    profile = _active_profile(db, primary)
    lane_rule = None
    if tier is not None and tier.rate_source == RATE_SOURCE_LANE:
        rules = rules if rules is not None else load_rules(db)
        lane_rule = lane_rule_for(origin.id if origin else None, primary, vehicle, on, rules)
        if lane_rule is None and profile is None:
            truck = vehicle.truck_type.name if vehicle and vehicle.truck_type else "this truck"
            origin_name = origin.name if origin else "the start point"
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No lane rate for {truck} · {origin_name} → {primary.name}. "
                    "Add one in Trip Category & Rates → Driver Rates."
                ),
            )
    elif profile is None:
        raise HTTPException(
            status_code=400,
            detail=f'"{primary.name}" has no active trip profile. Set one on the location first.',
        )

    return SimpleNamespace(
        profile=profile,
        tier=tier,
        customer_id=tier.customer_id if tier is not None else None,
        lane_rule=lane_rule,
    )


def apply_plan(trip, plan) -> None:
    """Writes the planned category / customer / tier onto a trip."""
    trip.trip_rate_profile_id = plan.profile.id if plan.profile else None
    trip.customer_id = plan.customer_id
    trip.customer_tier_id = plan.tier.id if plan.tier else None


def preview_rates(db: Session, destinations: list, origin, vehicle, on: date, helper_count: int = 0) -> dict:
    """What a trip would pay (driver / helper 1st & next) and why, without
    saving anything -- the line under Trip Dispatch."""
    rules = load_rules(db)
    plan = plan_trip(db, destinations, origin, vehicle, on, rules=rules)
    primary = destinations[0]
    draft = SimpleNamespace(
        trip_rate_profile=plan.profile,
        trip_rate_profile_id=plan.profile.id if plan.profile else None,
        vehicle_unit=vehicle,
        origin_store_id=origin.id if origin else None,
        destination_store=primary,
        destination_store_id=primary.id,
        trip_helpers=[None] * helper_count,
    )
    rates = resolve_trip_rates(draft, on, rules)
    return {
        "customer": plan.tier.customer.name if plan.tier else None,
        "tier": plan.tier.name if plan.tier else None,
        "rate_source": plan.tier.rate_source if plan.tier else "trip_profile",
        "trip_category": plan.profile.profile_name if plan.profile else None,
        "driver_first_trip_rate": rates["driver_first_trip_rate"],
        "driver_next_trip_rate": rates["driver_next_trip_rate"],
        "helper_first_trip_rate": rates["helper_first_trip_rate"],
        "helper_next_trip_rate": rates["helper_next_trip_rate"],
        "source": rates["rate_source"],
    }
