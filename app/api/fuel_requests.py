# app/api/fuel_requests.py
#
# Driver fuel requests. Driver (mobile Fuel tab) sends an odometer photo,
# plate number and city -> coordinator admin (web Fuel Requests page)
# issues a fuel code + liters -> driver fuels up and uploads the receipt
# -> coordinator admin confirms it (Completed) or sends it back.
# See app/models/fuel_request.py for the statuses.

from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role_or_module
from app.models.fuel_request import FuelRequest
from app.models.user import User, UserRole
from app.services.file_service import FileService
from app.utils.timezone import utc_to_ph
from app.utils.user_display import display_name

router = APIRouter(prefix="/fuel-requests", tags=["Fuel Requests"])

# Requests still in progress -- a driver may only have one at a time.
OPEN_STATUSES = ("pending", "issued", "returned", "receipt_submitted")

# What the coordinator admin still has to act on.
NEEDS_ACTION_STATUSES = ("pending", "receipt_submitted")

_require_coordinator = require_role_or_module(
    roles=["coordinator_admin"], module_key="fleet_management.fuel_requests"
)


def _fmt(dt):
    return utc_to_ph(dt).strftime("%b %d, %Y %I:%M %p") if dt else None


def _serialize(req: FuelRequest) -> dict:
    return {
        "id": req.id,
        "status": req.status,
        "driver_name": display_name(req.driver) if req.driver else None,
        "plate_number": req.plate_number,
        "city": req.city,
        "odo_photo_url": req.odo_photo_url,
        "fuel_code": req.fuel_code,
        "liters": float(req.liters) if req.liters is not None else None,
        "issued_by": display_name(req.issued_by) if req.issued_by else None,
        "issued_at": _fmt(req.issued_at),
        "receipt_photo_url": req.receipt_photo_url,
        "receipt_submitted_at": _fmt(req.receipt_submitted_at),
        "completed_by": display_name(req.completed_by) if req.completed_by else None,
        "completed_at": _fmt(req.completed_at),
        "note": req.note,
        "created_at": _fmt(req.created_at),
    }


def _query(db: Session):
    return db.query(FuelRequest).options(
        joinedload(FuelRequest.driver).joinedload(User.employee),
        joinedload(FuelRequest.issued_by).joinedload(User.employee),
        joinedload(FuelRequest.completed_by).joinedload(User.employee),
    )


def _require_image(upload: UploadFile, label: str):
    if upload is None or not upload.filename:
        raise HTTPException(status_code=400, detail=f"{label} is required.")
    if not (upload.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail=f"{label} must be an image.")


def _get_locked(db: Session, request_id: int) -> FuelRequest:
    req = (
        db.query(FuelRequest)
        .filter(FuelRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="Fuel request not found.")
    return req


def _is_driver(user: User) -> bool:
    return user.role == UserRole.DRIVER or str(user.role).lower().endswith("driver")


# =====================================================================
# DRIVER
# =====================================================================
@router.post("")
def create_fuel_request(
    plate_number: str = Form(...),
    city: str = Form(...),
    odo_photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_driver(current_user):
        raise HTTPException(status_code=403, detail="Only drivers can request fuel.")

    plate_number = plate_number.strip().upper()
    city = city.strip()
    if not plate_number:
        raise HTTPException(status_code=400, detail="Plate number is required.")
    if not city:
        raise HTTPException(status_code=400, detail="City is required.")
    _require_image(odo_photo, "Odometer photo")

    open_request = (
        db.query(FuelRequest.id)
        .filter(
            FuelRequest.user_id == current_user.id,
            FuelRequest.status.in_(OPEN_STATUSES),
        )
        .first()
    )
    if open_request:
        raise HTTPException(
            status_code=400,
            detail="You still have a fuel request in progress. Finish it first.",
        )

    req = FuelRequest(
        user_id=current_user.id,
        employee_id=current_user.employee_id,
        plate_number=plate_number,
        city=city,
        odo_photo_url="",
        status="pending",
    )
    db.add(req)
    db.flush()
    req.odo_photo_url = FileService().upload(odo_photo, f"fuel_requests/{req.id}/odo")
    db.commit()

    return _serialize(_query(db).filter(FuelRequest.id == req.id).first())


@router.get("/mine")
def list_my_fuel_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        _query(db)
        .filter(FuelRequest.user_id == current_user.id)
        .order_by(FuelRequest.created_at.desc())
        .limit(50)
        .all()
    )
    return [_serialize(r) for r in rows]


@router.post("/{request_id}/receipt")
def submit_fuel_receipt(
    request_id: int,
    receipt_photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_locked(db, request_id)
    if req.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Fuel request not found.")
    if req.status not in ("issued", "returned"):
        raise HTTPException(
            status_code=400,
            detail="A receipt can only be sent after the fuel code is issued.",
        )
    _require_image(receipt_photo, "Receipt photo")

    req.receipt_photo_url = FileService().upload(
        receipt_photo, f"fuel_requests/{req.id}/receipt"
    )
    req.receipt_submitted_at = datetime.utcnow()
    req.status = "receipt_submitted"
    db.commit()

    return _serialize(_query(db).filter(FuelRequest.id == req.id).first())


@router.post("/{request_id}/cancel")
def cancel_fuel_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_locked(db, request_id)
    if req.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Fuel request not found.")
    if req.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Only a request still waiting for a fuel code can be cancelled.",
        )
    req.status = "cancelled"
    db.commit()
    return {"message": "Fuel request cancelled."}


# =====================================================================
# COORDINATOR ADMIN (web)
# =====================================================================
@router.get("")
def list_fuel_requests(
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    """`status`: a single status, "open" (everything still in progress),
    or omitted for all. Newest first."""
    q = _query(db)
    if status == "open":
        q = q.filter(FuelRequest.status.in_(OPEN_STATUSES))
    elif status == "needs_action":
        q = q.filter(FuelRequest.status.in_(NEEDS_ACTION_STATUSES))
    elif status:
        q = q.filter(FuelRequest.status == status)
    rows = q.order_by(FuelRequest.created_at.desc()).limit(300).all()
    return [_serialize(r) for r in rows]


@router.get("/alerts")
def fuel_request_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    """For the web bell: requests waiting for a fuel code or a receipt
    check, oldest first."""
    rows = (
        _query(db)
        .filter(FuelRequest.status.in_(NEEDS_ACTION_STATUSES))
        .order_by(FuelRequest.updated_at.asc())
        .all()
    )
    return [_serialize(r) for r in rows]


@router.get("/{request_id}")
def get_fuel_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    req = _query(db).filter(FuelRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Fuel request not found.")
    return _serialize(req)


@router.post("/{request_id}/issue")
def issue_fuel_code(
    request_id: int,
    fuel_code: str = Body(..., embed=True),
    liters: float = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    req = _get_locked(db, request_id)
    if req.status != "pending":
        raise HTTPException(
            status_code=400, detail="This request already has a fuel code."
        )
    fuel_code = (fuel_code or "").strip()
    if not fuel_code:
        raise HTTPException(status_code=400, detail="Fuel code is required.")
    try:
        liters_value = Decimal(str(liters)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="Invalid liters.")
    if liters_value <= 0 or liters_value > 1000:
        raise HTTPException(
            status_code=400, detail="Liters must be more than 0 and at most 1,000."
        )

    req.fuel_code = fuel_code
    req.liters = liters_value
    req.issued_by_user_id = current_user.id
    req.issued_at = datetime.utcnow()
    req.status = "issued"
    db.commit()
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first())


@router.post("/{request_id}/decline")
def decline_fuel_request(
    request_id: int,
    reason: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    req = _get_locked(db, request_id)
    if req.status != "pending":
        raise HTTPException(
            status_code=400, detail="Only a request waiting for a fuel code can be declined."
        )
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required.")
    req.status = "declined"
    req.note = reason
    req.completed_by_user_id = current_user.id
    req.completed_at = datetime.utcnow()
    db.commit()
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first())


@router.post("/{request_id}/complete")
def complete_fuel_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    req = _get_locked(db, request_id)
    if req.status != "receipt_submitted":
        raise HTTPException(
            status_code=400, detail="There's no receipt waiting to be confirmed."
        )
    req.status = "completed"
    req.note = None
    req.completed_by_user_id = current_user.id
    req.completed_at = datetime.utcnow()
    db.commit()
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first())


@router.post("/{request_id}/return")
def return_fuel_receipt(
    request_id: int,
    reason: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    """Receipt is wrong/unreadable -- the driver uploads a new one."""
    req = _get_locked(db, request_id)
    if req.status != "receipt_submitted":
        raise HTTPException(
            status_code=400, detail="There's no receipt waiting to be confirmed."
        )
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required.")
    req.status = "returned"
    req.note = reason
    db.commit()
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first())
