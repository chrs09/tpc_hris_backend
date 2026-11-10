"""Customers -> Customer Chart: the customer master as a tree (like the
Org Chart). Customers (with sub-customers) -> their tiers (T1, T1.5, T2,
... fully dynamic, each with a rate source) -> the locations under each
tier. Trip Dispatch reads it to start from the customer and to preview the
rate (app/services/customer_tiers.py)."""

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.customer import RATE_SOURCES, Customer, CustomerTier
from app.models.stores import Store
from app.models.trips import Trip
from app.models.truck_type import TruckType
from app.models.vehicle_unit import VehicleUnit
from app.services.customer_tiers import preview_rates, tier_truck_type_ids

router = APIRouter(prefix="/admin/customer-chart", tags=["Customer Chart"])

COMPANY_NAME = "Tytan Prime Corporation"

# Editing the chart: the Customers page's editors. Reading it: also the
# trip pages that dispatch from it (same list as GET /admin/stores).
_require_editor = require_role_or_module(
    roles=["admin", "superadmin", "coordinator_admin"], module_key="customers.customers"
)
_require_viewer = require_role_or_module(
    roles=["admin", "superadmin", "coordinator_admin", "coordinator"],
    module_key=[
        "customers.customers",
        "trip_management.trip_assignment",
        "trip_management.trip_dashboard",
        "trip_management.trips",
    ],
)


# =========================
# READ
# =========================
def _tier_payload(tier: CustomerTier, counts: dict) -> dict:
    return {
        "id": tier.id,
        "customer_id": tier.customer_id,
        "name": tier.name,
        "description": tier.description,
        "rate_source": tier.rate_source,
        "truck_type_ids": tier_truck_type_ids(tier),
        "sort_order": tier.sort_order,
        "is_active": bool(tier.is_active),
        "location_count": counts.get(tier.id, 0),
    }


@router.get("")
def get_customer_chart(
    db: Session = Depends(get_db),
    current_user=Depends(_require_viewer),
):
    """The whole chart: every customer (flat, with parent_id) and its tiers
    with how many locations each has, plus the unassigned count."""
    counts = dict(
        db.query(Store.customer_tier_id, func.count(Store.id))
        .filter(Store.customer_tier_id.isnot(None))
        .group_by(Store.customer_tier_id)
        .all()
    )
    customers = (
        db.query(Customer)
        .options(joinedload(Customer.tiers))
        .order_by(Customer.sort_order.asc(), Customer.name.asc())
        .all()
    )
    unassigned = (
        db.query(func.count(Store.id)).filter(Store.customer_tier_id.is_(None)).scalar() or 0
    )
    return {
        "company": COMPANY_NAME,
        "customers": [
            {
                "id": c.id,
                "name": c.name,
                "code": c.code,
                "parent_id": c.parent_id,
                "notes": c.notes,
                "is_active": bool(c.is_active),
                "sort_order": c.sort_order,
                "tiers": [_tier_payload(t, counts) for t in c.tiers],
                "location_count": sum(counts.get(t.id, 0) for t in c.tiers),
            }
            for c in customers
        ],
        "unassigned_count": unassigned,
        "rate_sources": [
            {"value": "lane", "label": "Lane rate (truck type + origin → location)"},
            {"value": "trip_profile", "label": "Trip profile of the location"},
        ],
        "truck_types": [
            {"id": t.id, "name": t.name}
            for t in db.query(TruckType).order_by(TruckType.name.asc()).all()
        ],
    }


def _location_row(store: Store) -> dict:
    tier = store.customer_tier
    return {
        "id": store.id,
        "name": store.name,
        "area": store.area,
        "is_hub": bool(store.is_hub),
        "is_supplier": bool(store.is_supplier),
        "trip_profile": (
            store.trip_rate_profile.profile_name if store.trip_rate_profile else None
        ),
        "customer_tier_id": store.customer_tier_id,
        "tier_label": f"{tier.customer.name} · {tier.name}" if tier else None,
    }


@router.get("/tiers/{tier_id}/locations")
def get_tier_locations(
    tier_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(_require_viewer),
):
    stores = (
        db.query(Store)
        .options(joinedload(Store.trip_rate_profile))
        .filter(Store.customer_tier_id == tier_id)
        .order_by(Store.is_hub.desc(), Store.name.asc())
        .all()
    )
    return [_location_row(s) for s in stores]


@router.get("/locations")
def search_locations(
    q: str = "",
    unassigned: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(_require_viewer),
):
    """Locations to add to a tier: by name / area, or only unassigned."""
    query = db.query(Store).options(joinedload(Store.trip_rate_profile))
    if unassigned:
        query = query.filter(Store.customer_tier_id.is_(None))
    term = q.strip()
    if term:
        like = f"%{term}%"
        query = query.filter(or_(Store.name.ilike(like), Store.area.ilike(like)))
    stores = query.order_by(Store.name.asc()).limit(max(1, min(limit, 200))).all()
    return [_location_row(s) for s in stores]


# =========================
# CUSTOMERS
# =========================
class CustomerPayload(BaseModel):
    name: str | None = None
    code: str | None = None
    notes: str | None = None
    parent_id: int | None = None
    is_active: bool | None = None
    sort_order: int | None = None


def _get_customer(db: Session, customer_id: int) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
    return customer


def _check_parent(db: Session, customer: Customer | None, parent_id: int | None):
    """The parent must exist and not be the customer itself or below it."""
    if parent_id is None:
        return
    parent = _get_customer(db, parent_id)
    if customer is None:
        return
    node = parent
    while node is not None:
        if node.id == customer.id:
            raise HTTPException(
                status_code=400,
                detail="A customer can't be placed under itself or one of its sub-customers.",
            )
        node = db.get(Customer, node.parent_id) if node.parent_id else None


@router.post("/customers")
def create_customer(
    payload: CustomerPayload,
    db: Session = Depends(get_db),
    current_user=Depends(_require_editor),
):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Enter the customer's name.")
    _check_parent(db, None, payload.parent_id)
    customer = Customer(
        name=name,
        code=(payload.code or "").strip() or None,
        notes=(payload.notes or "").strip() or None,
        parent_id=payload.parent_id,
        is_active=True,
        sort_order=payload.sort_order or 0,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(customer)
    db.commit()
    return {"id": customer.id, "message": "Customer added."}


@router.patch("/customers/{customer_id}")
def update_customer(
    customer_id: int,
    payload: CustomerPayload,
    db: Session = Depends(get_db),
    current_user=Depends(_require_editor),
):
    customer = _get_customer(db, customer_id)
    sent = payload.model_fields_set
    if "name" in sent:
        name = (payload.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Enter the customer's name.")
        customer.name = name
    if "code" in sent:
        customer.code = (payload.code or "").strip() or None
    if "notes" in sent:
        customer.notes = (payload.notes or "").strip() or None
    if "parent_id" in sent:
        _check_parent(db, customer, payload.parent_id)
        customer.parent_id = payload.parent_id
    if "is_active" in sent and payload.is_active is not None:
        customer.is_active = payload.is_active
    if "sort_order" in sent and payload.sort_order is not None:
        customer.sort_order = payload.sort_order
    customer.updated_by = current_user.id
    db.commit()
    return {"message": "Customer saved."}


@router.delete("/customers/{customer_id}")
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(_require_editor),
):
    """Only an empty customer (no sub-customers, tiers or trips) is
    deleted; otherwise turn it off (is_active) instead."""
    customer = _get_customer(db, customer_id)
    if db.query(Customer.id).filter(Customer.parent_id == customer.id).first():
        raise HTTPException(
            status_code=400, detail="Move or remove its sub-customers first."
        )
    if customer.tiers:
        raise HTTPException(
            status_code=400,
            detail="Remove its tiers first, or turn the customer off instead.",
        )
    if db.query(Trip.id).filter(Trip.customer_id == customer.id).first():
        raise HTTPException(
            status_code=400, detail="It has trips. Turn the customer off instead."
        )
    db.delete(customer)
    db.commit()
    return {"message": "Customer removed."}


# =========================
# TIERS
# =========================
class TierPayload(BaseModel):
    name: str | None = None
    description: str | None = None
    rate_source: str | None = None
    truck_type_ids: list[int] | None = None
    is_active: bool | None = None
    sort_order: int | None = None


def _get_tier(db: Session, tier_id: int) -> CustomerTier:
    tier = db.query(CustomerTier).filter(CustomerTier.id == tier_id).first()
    if not tier:
        raise HTTPException(status_code=404, detail="Tier not found.")
    return tier


def _clean_tier_name(db: Session, customer_id: int, name: str | None, tier_id=None) -> str:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Enter the tier's name (e.g. T1).")
    clash = (
        db.query(CustomerTier.id)
        .filter(
            CustomerTier.customer_id == customer_id,
            func.lower(CustomerTier.name) == name.lower(),
            *([CustomerTier.id != tier_id] if tier_id else []),
        )
        .first()
    )
    if clash:
        raise HTTPException(status_code=400, detail=f"This customer already has a tier {name}.")
    return name


def _check_rate_source(value: str | None) -> str:
    if value not in RATE_SOURCES:
        raise HTTPException(status_code=400, detail="Pick where the tier's rate comes from.")
    return value


@router.post("/customers/{customer_id}/tiers")
def create_tier(
    customer_id: int,
    payload: TierPayload,
    db: Session = Depends(get_db),
    current_user=Depends(_require_editor),
):
    customer = _get_customer(db, customer_id)
    tier = CustomerTier(
        customer_id=customer.id,
        name=_clean_tier_name(db, customer.id, payload.name),
        description=(payload.description or "").strip() or None,
        rate_source=_check_rate_source(payload.rate_source or "trip_profile"),
        truck_type_ids=json.dumps(payload.truck_type_ids or []),
        sort_order=(
            payload.sort_order
            if payload.sort_order is not None
            else len(customer.tiers)
        ),
        is_active=True,
    )
    db.add(tier)
    db.commit()
    return {"id": tier.id, "message": f"Tier {tier.name} added."}


@router.patch("/tiers/{tier_id}")
def update_tier(
    tier_id: int,
    payload: TierPayload,
    db: Session = Depends(get_db),
    current_user=Depends(_require_editor),
):
    tier = _get_tier(db, tier_id)
    sent = payload.model_fields_set
    if "name" in sent:
        tier.name = _clean_tier_name(db, tier.customer_id, payload.name, tier.id)
    if "description" in sent:
        tier.description = (payload.description or "").strip() or None
    if "rate_source" in sent:
        tier.rate_source = _check_rate_source(payload.rate_source)
    if "truck_type_ids" in sent:
        tier.truck_type_ids = json.dumps(payload.truck_type_ids or [])
    if "is_active" in sent and payload.is_active is not None:
        tier.is_active = payload.is_active
    if "sort_order" in sent and payload.sort_order is not None:
        tier.sort_order = payload.sort_order
    db.commit()
    return {"message": f"Tier {tier.name} saved."}


@router.delete("/tiers/{tier_id}")
def delete_tier(
    tier_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(_require_editor),
):
    tier = _get_tier(db, tier_id)
    if db.query(Store.id).filter(Store.customer_tier_id == tier.id).first():
        raise HTTPException(
            status_code=400, detail="Move its locations to another tier first."
        )
    if db.query(Trip.id).filter(Trip.customer_tier_id == tier.id).first():
        raise HTTPException(
            status_code=400, detail="It has trips. Turn the tier off instead."
        )
    db.delete(tier)
    db.commit()
    return {"message": "Tier removed."}


# =========================
# LOCATIONS
# =========================
class LocationsPayload(BaseModel):
    store_ids: list[int]


@router.post("/tiers/{tier_id}/locations")
def add_locations(
    tier_id: int,
    payload: LocationsPayload,
    db: Session = Depends(get_db),
    current_user=Depends(_require_editor),
):
    """Puts these locations under the tier (moving them from wherever they
    were -- a location has one customer). Past trips keep theirs."""
    tier = _get_tier(db, tier_id)
    moved = (
        db.query(Store)
        .filter(Store.id.in_(payload.store_ids or [0]))
        .update({Store.customer_tier_id: tier.id}, synchronize_session=False)
    )
    db.commit()
    return {"message": f"{moved} location{'s' if moved != 1 else ''} moved to {tier.name}."}


@router.post("/locations/unassign")
def unassign_locations(
    payload: LocationsPayload,
    db: Session = Depends(get_db),
    current_user=Depends(_require_editor),
):
    removed = (
        db.query(Store)
        .filter(Store.id.in_(payload.store_ids or [0]))
        .update({Store.customer_tier_id: None}, synchronize_session=False)
    )
    db.commit()
    return {"message": f"{removed} location{'s' if removed != 1 else ''} removed from the chart."}


# =========================
# RATE PREVIEW (Trip Dispatch)
# =========================
class PreviewPayload(BaseModel):
    origin_store_id: int | None = None
    destination_store_ids: list[int]
    vehicle_unit_id: int | None = None
    helper_count: int = 0


@router.post("/rate-preview")
def rate_preview(
    payload: PreviewPayload,
    db: Session = Depends(get_db),
    current_user=Depends(_require_viewer),
):
    """What the trip being dispatched would pay, or why it can't go (400,
    same message dispatch would give)."""
    if not payload.destination_store_ids:
        raise HTTPException(status_code=400, detail="Pick a destination.")
    stores = {
        s.id: s
        for s in db.query(Store).filter(Store.id.in_(payload.destination_store_ids)).all()
    }
    destinations = [stores[i] for i in payload.destination_store_ids if i in stores]
    if not destinations:
        raise HTTPException(status_code=400, detail="Pick a destination.")
    origin = db.get(Store, payload.origin_store_id) if payload.origin_store_id else None
    vehicle = db.get(VehicleUnit, payload.vehicle_unit_id) if payload.vehicle_unit_id else None
    today: date = datetime.now(ZoneInfo("Asia/Manila")).date()
    return preview_rates(db, destinations, origin, vehicle, today, payload.helper_count)
