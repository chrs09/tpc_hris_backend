"""Driver / helper rates by trip category, truck type and lane, each
with an effective date (Trip Management -> Trip Category & Rates ->
Driver Rates). How a trip picks its rate: app/services/trip_rates.py."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.stores import Store
from app.models.TripRate import TripRateProfile
from app.models.trip_rate_rule import TripRateRule
from app.models.truck_type import TruckType
from app.models.user import User
from app.services.payroll_lock import latest_locked_end
from app.services.trip_rates import RATE_FIELDS

router = APIRouter(prefix="/trip-rate-rules", tags=["Trip Rate Rules"])

_require_rates = require_role_or_module(
    roles=["coordinator_admin"], module_key="trip_management.trip_categories"
)


def _num(value):
    return float(value) if value is not None else None


def _serialize(rule: TripRateRule) -> dict:
    return {
        "id": rule.id,
        "trip_rate_profile_id": rule.trip_rate_profile_id,
        "trip_rate_profile": rule.trip_rate_profile.profile_name if rule.trip_rate_profile else None,
        "truck_type_id": rule.truck_type_id,
        "truck_type": rule.truck_type.name if rule.truck_type else None,
        "origin_store_id": rule.origin_store_id,
        "origin_store": rule.origin_store.name if rule.origin_store else None,
        "destination_area": rule.destination_area,
        "destination_store_id": rule.destination_store_id,
        "destination_store": rule.destination_store.name if rule.destination_store else None,
        **{field: _num(getattr(rule, field)) for field in RATE_FIELDS},
        "effective_from": rule.effective_from.isoformat(),
        "notes": rule.notes,
    }


@router.get("")
def list_rate_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_rates),
):
    rules = (
        db.query(TripRateRule)
        .options(
            joinedload(TripRateRule.trip_rate_profile),
            joinedload(TripRateRule.truck_type),
            joinedload(TripRateRule.origin_store),
            joinedload(TripRateRule.destination_store),
        )
        .order_by(TripRateRule.effective_from.desc(), TripRateRule.id.desc())
        .all()
    )
    areas = sorted(
        {a for (a,) in db.query(Store.area).filter(Store.area.isnot(None)).distinct() if a}
    )
    locked_until = latest_locked_end(db)
    return {
        "rules": [_serialize(r) for r in rules],
        "options": {
            "categories": [
                {"id": p.id, "name": p.profile_name, "is_active": p.is_active}
                for p in db.query(TripRateProfile).order_by(TripRateProfile.profile_name).all()
            ],
            "truck_types": [
                {"id": t.id, "name": t.name}
                for t in db.query(TruckType).filter(TruckType.is_active.is_(True)).order_by(TruckType.name).all()
            ],
            # From: any location -- hubs, then suppliers, then customers.
            "origins": [
                {"id": s.id, "name": s.name, "is_hub": s.is_hub, "is_supplier": s.is_supplier}
                for s in db.query(Store)
                .order_by(Store.is_hub.desc(), Store.is_supplier.desc(), Store.name)
                .all()
            ],
            # To: any outlet (customers and supplier locations).
            "destinations": [
                {"id": s.id, "name": s.name, "area": s.area, "is_supplier": s.is_supplier}
                for s in db.query(Store)
                .filter(Store.is_hub.is_(False))
                .order_by(Store.name)
                .all()
            ],
            "areas": areas,
        },
        # Rates in effect up to this date are part of locked payroll.
        "locked_until": locked_until.isoformat() if locked_until else None,
    }


class RuleIn(BaseModel):
    trip_rate_profile_id: int | None = None
    truck_type_id: int | None = None
    origin_store_id: int | None = None
    destination_area: str | None = None
    destination_store_id: int | None = None
    driver_first_trip_rate: float | None = None
    driver_next_trip_rate: float | None = None
    helper_first_trip_rate: float | None = None
    helper_next_trip_rate: float | None = None
    effective_from: date
    notes: str | None = None


def _guard_locked(db: Session, effective_from: date, verb: str):
    locked_until = latest_locked_end(db)
    if locked_until and effective_from <= locked_until:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Payroll is locked up to {locked_until:%b %d, %Y}, so a rate in effect "
                f"on or before then can't be {verb}. Add a new rate with a later "
                "effective date instead."
            ),
        )


def _apply(db: Session, rule: TripRateRule, payload: RuleIn):
    area = (payload.destination_area or "").strip() or None
    rates = {field: getattr(payload, field) for field in RATE_FIELDS}
    if all(v is None for v in rates.values()):
        raise HTTPException(status_code=400, detail="Enter at least one rate.")
    if any(v is not None and v < 0 for v in rates.values()):
        raise HTTPException(status_code=400, detail="Rates can't be negative.")

    duplicate = (
        db.query(TripRateRule)
        .filter(
            TripRateRule.trip_rate_profile_id == payload.trip_rate_profile_id,
            TripRateRule.truck_type_id == payload.truck_type_id,
            TripRateRule.origin_store_id == payload.origin_store_id,
            TripRateRule.destination_area == area,
            TripRateRule.destination_store_id == payload.destination_store_id,
            TripRateRule.effective_from == payload.effective_from,
            TripRateRule.id != (rule.id or 0),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=400,
            detail="A rate for the same category, truck, lane and effective date already exists.",
        )

    rule.trip_rate_profile_id = payload.trip_rate_profile_id
    rule.truck_type_id = payload.truck_type_id
    rule.origin_store_id = payload.origin_store_id
    # An exact outlet replaces the area.
    rule.destination_store_id = payload.destination_store_id or None
    rule.destination_area = None if rule.destination_store_id else area
    for field, value in rates.items():
        setattr(rule, field, value)
    rule.effective_from = payload.effective_from
    rule.notes = (payload.notes or "").strip() or None


@router.post("")
def create_rate_rule(
    payload: RuleIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_rates),
):
    _guard_locked(db, payload.effective_from, "added")
    rule = TripRateRule(created_by=current_user.id)
    _apply(db, rule, payload)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _serialize(rule)


def _get(db: Session, rule_id: int) -> TripRateRule:
    rule = db.query(TripRateRule).filter(TripRateRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rate not found.")
    return rule


@router.put("/{rule_id}")
def update_rate_rule(
    rule_id: int,
    payload: RuleIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_rates),
):
    rule = _get(db, rule_id)
    _guard_locked(db, rule.effective_from, "changed")
    _guard_locked(db, payload.effective_from, "changed")
    _apply(db, rule, payload)
    rule.updated_by = current_user.id
    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)
    return _serialize(rule)


@router.delete("/{rule_id}")
def delete_rate_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_rates),
):
    rule = _get(db, rule_id)
    _guard_locked(db, rule.effective_from, "deleted")
    db.delete(rule)
    db.commit()
    return {"message": "Rate deleted."}
