"""Which unit a driver may take on a trip.

- Each driver has one assigned unit (VehicleUnit.assigned_driver_id);
  Trip Assignment picks it automatically.
- A unit with an open "In repair" maintenance record can't be dispatched
  -- the coordinator is told why (type, since when, expected back).
- Any other unit is allowed with a reason (e.g. a loaded unit whose
  driver isn't around today). No approval -- the reason is saved on the
  trip and shown to the reviewers. A driver without an assigned unit
  taking a unit nobody owns needs no reason.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.vehicle_maintenance import VehicleMaintenance
from app.models.vehicle_unit import VehicleUnit

UNIT_REASONS = {
    "ASSIGNED_UNIT_IN_REPAIR": "Assigned unit is under repair",
    "ASSIGNED_UNIT_BUSY": "Assigned unit not loaded / on another trip",
    "UNIT_DRIVER_ABSENT": "The unit's driver is not around (load must go out today)",
    "NEW_DRIVER": "New driver -- no assigned unit yet",
    "URGENT": "Urgent delivery",
    "OTHER": "Other",
}


def open_repair(db: Session, vehicle_unit_id: int | None):
    if not vehicle_unit_id:
        return None
    return (
        db.query(VehicleMaintenance)
        .filter(
            VehicleMaintenance.vehicle_unit_id == vehicle_unit_id,
            VehicleMaintenance.in_repair.is_(True),
        )
        .order_by(VehicleMaintenance.service_date.desc())
        .first()
    )


def repair_info(record) -> dict | None:
    if not record:
        return None
    since = record.service_date.strftime("%b %d") if record.service_date else None
    back = (
        record.expected_return_date.strftime("%b %d")
        if record.expected_return_date
        else None
    )
    text = f"Under repair: {record.maintenance_type}"
    if record.description:
        text += f" ({record.description})"
    if since:
        text += f", since {since}"
    if back:
        text += f", expected back {back}"
    return {
        "maintenance_id": record.id,
        "maintenance_type": record.maintenance_type,
        "description": record.description,
        "since": record.service_date,
        "expected_return_date": record.expected_return_date,
        "text": text + ".",
    }


def unit_label(unit) -> str:
    return unit.plate_number or unit.unit_code or f"Unit #{unit.id}"


def assigned_unit_of(db: Session, driver_user_id: int | None):
    if not driver_user_id:
        return None
    return (
        db.query(VehicleUnit)
        .filter(VehicleUnit.assigned_driver_id == driver_user_id)
        .first()
    )


def check_unit_for_trip(
    db: Session,
    driver_user_id: int,
    vehicle,
    reason_type: str | None,
    reason_note: str | None,
) -> tuple[str | None, str | None]:
    """Raises if the unit can't go; otherwise (reason_type, reason_text) to
    save on the trip -- (None, None) when it's the driver's own unit."""
    repair = repair_info(open_repair(db, vehicle.id))
    if repair:
        raise HTTPException(
            status_code=400,
            detail=f"{unit_label(vehicle)} can't be dispatched. {repair['text']} Pick another unit.",
        )

    own = assigned_unit_of(db, driver_user_id)
    if own and own.id == vehicle.id:
        return None, None
    if not own and not vehicle.assigned_driver_id:
        # Driver without a unit in a unit nobody owns.
        return (reason_type or None), _reason_text(reason_type, reason_note) if reason_type else None

    reason_type = (reason_type or "").strip().upper()
    note = (reason_note or "").strip()
    if reason_type not in UNIT_REASONS:
        owner = (
            f"{unit_label(own)} is this driver's unit"
            if own
            else "This driver has no assigned unit"
        )
        raise HTTPException(
            status_code=400,
            detail=f"{owner} -- give the reason for using {unit_label(vehicle)}.",
        )
    if reason_type == "OTHER" and not note:
        raise HTTPException(status_code=400, detail="Describe the reason for using this unit.")
    return reason_type, _reason_text(reason_type, note)


def _reason_text(reason_type: str | None, note: str | None) -> str | None:
    if not reason_type:
        return None
    label = UNIT_REASONS.get(reason_type, reason_type)
    note = (note or "").strip()
    if reason_type == "OTHER":
        return note
    return f"{label} -- {note}" if note else label


def trip_unit_flags(trip) -> dict:
    """For trip lists / details: the Urgent label and the unit reason."""
    return {
        "is_urgent": bool(getattr(trip, "is_urgent", False)),
        "unit_reason_type": getattr(trip, "unit_reason_type", None),
        "unit_reason": getattr(trip, "unit_reason", None),
    }
