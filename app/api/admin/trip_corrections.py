"""Trip Management -> Correction Requests / Correction History.

Coordinators / operations request a correction to a finished trip with a
reason; Finance approves (the trip changes, its old values are kept on the
correction) or rejects. Rules: app/services/trip_corrections.py."""

import json
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.employees import Employee
from app.models.trip_bypass_log import TripBypassLog
from app.models.trip_correction import TripCorrection
from app.models.trips import Trip
from app.models.user import User
from app.models.vehicle_unit import VehicleUnit
from app.services import trip_corrections as C
from app.services.user_roles import driver_user_condition
from app.utils.timezone import utc_to_ph
from app.utils.user_display import display_name

router = APIRouter(prefix="/trip-corrections", tags=["Trip Corrections"])

REQUESTER_ROLES = ["superadmin", "coordinator_admin", "coordinator"]
REQUESTER_KEY = "trip_management.trip_corrections"
APPROVER_ROLES = ["admin", "superadmin"]
APPROVER_KEY = "finance.finance_trips"

_require_requester = require_role_or_module(roles=REQUESTER_ROLES, module_key=REQUESTER_KEY)
_require_approver = require_role_or_module(roles=APPROVER_ROLES, module_key=APPROVER_KEY)
_require_viewer = require_role_or_module(
    roles=REQUESTER_ROLES + APPROVER_ROLES, module_key=[REQUESTER_KEY, APPROVER_KEY]
)


def _role(user) -> str:
    return (getattr(user.role, "value", user.role) or "").lower()


def _can(db: Session, user: User, roles: list[str], key: str) -> bool:
    """Same rule as require_role_or_module, without raising."""
    try:
        require_role_or_module(roles=roles, module_key=key)(None, user, db)
        return True
    except HTTPException:
        return False


def _fmt(dt):
    return utc_to_ph(dt).strftime("%b %d, %Y %I:%M %p") if dt else None


def _serialize(db: Session, c: TripCorrection) -> dict:
    requested = json.loads(c.requested or "{}")
    original = json.loads(c.original or "{}")
    trip = c.trip
    return {
        "id": c.id,
        "trip_id": c.trip_id,
        "trip_code": trip.trip_code if trip else None,
        "ticket_no": trip.ticket_no if trip else None,
        "trip_status": getattr(trip.status, "value", trip.status) if trip else None,
        "driver_name": display_name(trip.driver) if trip and trip.driver else None,
        "status": c.status,
        "reason": c.reason,
        "changes": [
            {
                "field": field,
                "label": C.FIELD_LABELS.get(field, field),
                "from": C.describe(db, field, original.get(field)),
                "to": C.describe(db, field, value),
            }
            for field, value in requested.items()
        ],
        "requested_by": display_name(c.requested_by) if c.requested_by else None,
        "requested_by_user_id": c.requested_by_user_id,
        "requested_at": _fmt(c.requested_at),
        "decided_by": display_name(c.decided_by) if c.decided_by else None,
        "decided_at": _fmt(c.decided_at),
        "decision_note": c.decision_note,
    }


@router.get("")
def list_corrections(
    view: str = "requests",  # requests = pending; history = decided / cancelled
    q: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_viewer),
):
    query = (
        db.query(TripCorrection)
        .options(
            joinedload(TripCorrection.trip).joinedload(Trip.driver).joinedload(User.employee),
            joinedload(TripCorrection.requested_by).joinedload(User.employee),
            joinedload(TripCorrection.decided_by).joinedload(User.employee),
        )
        .join(Trip, Trip.id == TripCorrection.trip_id)
    )
    if view == "history":
        query = query.filter(TripCorrection.status != "pending").order_by(
            TripCorrection.decided_at.desc(), TripCorrection.id.desc()
        )
    else:
        query = query.filter(TripCorrection.status == "pending").order_by(TripCorrection.requested_at.asc())
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        query = query.filter(or_(Trip.trip_code.ilike(like), Trip.ticket_no.ilike(like)))
    rows = query.limit(300).all()
    return {
        "corrections": [_serialize(db, c) for c in rows],
        "pending_count": db.query(TripCorrection).filter(TripCorrection.status == "pending").count(),
        "can_request": _can(db, current_user, REQUESTER_ROLES, REQUESTER_KEY),
        "can_approve": _can(db, current_user, APPROVER_ROLES, APPROVER_KEY),
    }


@router.get("/trip-search")
def search_correctable_trips(
    q: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_requester),
):
    """Finished, not-cleared trips matching a trip code or shipment number."""
    term = q.strip()
    if len(term) < 3:
        return []
    like = f"%{term}%"
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.driver).joinedload(User.employee))
        .filter(
            Trip.status.in_(C.CORRECTABLE),
            Trip.is_archived.is_(False),
            or_(Trip.trip_code.ilike(like), Trip.ticket_no.ilike(like)),
        )
        .order_by(Trip.id.desc())
        .limit(15)
        .all()
    )
    return [
        {
            "id": t.id,
            "trip_code": t.trip_code,
            "ticket_no": t.ticket_no,
            "driver_name": display_name(t.driver) if t.driver else None,
            "trip_date": _fmt(t.start_time),
            "status": getattr(t.status, "value", t.status),
        }
        for t in trips
    ]


@router.get("/trip/{trip_id}")
def get_trip_for_correction(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_requester),
):
    """The trip's current values and the choices for the correction form."""
    trip = db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    C.check_correctable(db, trip)
    pending = (
        db.query(TripCorrection.id)
        .filter(TripCorrection.trip_id == trip.id, TripCorrection.status == "pending")
        .first()
    )
    drivers = (
        db.query(User)
        .options(joinedload(User.employee))
        .filter(driver_user_condition())
        .order_by(User.username.asc())
        .all()
    )
    helpers = (
        db.query(Employee)
        .filter(Employee.position.ilike("helper"))
        .order_by(Employee.first_name.asc())
        .all()
    )
    vehicles = db.query(VehicleUnit).order_by(VehicleUnit.unit_code.asc()).all()
    return {
        "trip": {
            "id": trip.id,
            "trip_code": trip.trip_code,
            "ticket_no": trip.ticket_no,
            "status": getattr(trip.status, "value", trip.status),
        },
        "current": C.current_values(db, trip),
        "pending_correction_id": pending[0] if pending else None,
        "options": {
            "drivers": [{"id": d.id, "label": display_name(d)} for d in drivers],
            "helpers": [{"id": h.id, "label": f"{h.first_name} {h.last_name}"} for h in helpers],
            "vehicles": [
                {"id": v.id, "label": " - ".join(dict.fromkeys(filter(None, [v.unit_code, v.plate_number])))}
                for v in vehicles
            ],
        },
    }


class CorrectionPayload(BaseModel):
    trip_id: int
    reason: str
    # Only the fields being corrected (see app/services/trip_corrections.FIELDS).
    changes: dict


@router.post("")
def request_correction(
    payload: CorrectionPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_requester),
):
    trip = db.get(Trip, payload.trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    C.check_correctable(db, trip)
    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Enter why the trip needs correcting.")
    if (
        db.query(TripCorrection.id)
        .filter(TripCorrection.trip_id == trip.id, TripCorrection.status == "pending")
        .first()
    ):
        raise HTTPException(
            status_code=400,
            detail="This trip already has a correction waiting for Finance.",
        )
    changes = C.changes_only(db, trip, payload.changes or {})
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing was changed.")
    warnings: list = []
    original = C.dry_run(db, trip, changes, warnings)
    if warnings:
        # Shown to Finance with the request (e.g. the rate was kept).
        reason = f"{reason}\n[Note: {'; '.join(warnings)}]"

    correction = TripCorrection(
        trip_id=trip.id,
        status="pending",
        reason=reason[:2000],
        requested=json.dumps(changes),
        original=json.dumps(original),
        requested_by_user_id=current_user.id,
        requested_at=datetime.utcnow(),
    )
    db.add(correction)
    db.commit()
    return {
        "id": correction.id,
        "message": "Correction sent to Finance for approval."
        + (f" Note: {'; '.join(warnings)}" if warnings else ""),
        "warnings": warnings,
    }


def _get_pending(db: Session, correction_id: int) -> TripCorrection:
    c = db.get(TripCorrection, correction_id)
    if not c:
        raise HTTPException(status_code=404, detail="Correction not found.")
    if c.status != "pending":
        raise HTTPException(status_code=400, detail="This correction was already decided.")
    return c


@router.post("/{correction_id}/approve")
def approve_correction(
    correction_id: int,
    note: str | None = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_approver),
):
    """Applies the correction to the trip; its replaced values are kept."""
    c = _get_pending(db, correction_id)
    trip = db.get(Trip, c.trip_id)
    C.check_correctable(db, trip)
    changes = json.loads(c.requested)
    c.original = json.dumps(C.apply(db, trip, changes))
    c.status = "approved"
    c.decided_by_user_id = current_user.id
    c.decided_at = datetime.utcnow()
    c.decision_note = (note or "").strip() or None
    db.add(
        TripBypassLog(
            trip_id=trip.id,
            action="correction",
            performed_by_user_id=current_user.id,
            reason=(
                f"Correction #{c.id} approved: "
                + ", ".join(C.FIELD_LABELS.get(f, f) for f in changes)
                + f". {c.reason}"
            )[:2000],
        )
    )
    db.commit()
    return {"message": "Correction approved and applied to the trip."}


@router.post("/{correction_id}/reject")
def reject_correction(
    correction_id: int,
    note: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_approver),
):
    c = _get_pending(db, correction_id)
    note = (note or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="Enter why it's rejected.")
    c.status = "rejected"
    c.decided_by_user_id = current_user.id
    c.decided_at = datetime.utcnow()
    c.decision_note = note[:2000]
    db.commit()
    return {"message": "Correction rejected. The trip wasn't changed."}


@router.post("/{correction_id}/cancel")
def cancel_correction(
    correction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_viewer),
):
    """The requester (or a superadmin) withdraws a pending correction."""
    c = _get_pending(db, correction_id)
    if c.requested_by_user_id != current_user.id and _role(current_user) != "superadmin":
        raise HTTPException(status_code=403, detail="Only the requester can cancel it.")
    c.status = "cancelled"
    c.decided_by_user_id = current_user.id
    c.decided_at = datetime.utcnow()
    db.commit()
    return {"message": "Correction cancelled."}


def corrected_trip_ids(db: Session, trip_ids) -> set[int]:
    """Trips with an approved correction (the "Corrected" badge)."""
    ids = [i for i in trip_ids if i]
    if not ids:
        return set()
    return {
        tid
        for (tid,) in db.query(TripCorrection.trip_id).filter(
            TripCorrection.trip_id.in_(ids), TripCorrection.status == "approved"
        )
    }
