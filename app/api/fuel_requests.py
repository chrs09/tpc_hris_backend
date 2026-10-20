# app/api/fuel_requests.py
#
# Driver fuel requests. Driver (mobile Fuel tab) sends an odometer photo,
# plate number and city -> coordinator admin (web Fuel Requests page)
# issues a fuel code + liters -> driver fuels up and uploads the receipt
# -> coordinator admin confirms it (Completed) or sends it back.
# When the Org Chart has heads with "Fuel Request" ticked above the
# driver, they approve it first (in order), before the fuel code.
# See app/models/fuel_request.py for the statuses.

from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role_or_module
from app.models.employees import Employee
from app.models.fuel_request import FuelRequest
from app.services.approval_chain import (
    acting_index,
    append_log,
    describe_chain,
    dump_chain,
    load_json_list,
    log_skipped,
    resolve_chain,
    skipped_for,
    team_scope,
)
from app.models.user import User, UserRole
from app.services.file_service import FileService
from app.utils.timezone import utc_to_ph
from app.utils.user_display import display_name

router = APIRouter(prefix="/fuel-requests", tags=["Fuel Requests"])

# Requests still in progress -- a driver may only have one at a time.
OPEN_STATUSES = ("pending", "issued", "returned", "receipt_submitted")

# What the coordinator admin still has to act on: see _needs_action_filter
# (pending -- once past the Org Chart heads -- and receipt_submitted).

_require_coordinator = require_role_or_module(
    roles=["coordinator_admin"], module_key="fleet_management.fuel_requests"
)


def _fmt(dt):
    return utc_to_ph(dt).strftime("%b %d, %Y %I:%M %p") if dt else None


def _needs_action_filter():
    # A pending request still with the Org Chart heads isn't the
    # coordinator's yet.
    return or_(
        (FuelRequest.status == "pending") & (FuelRequest.awaiting_approval.is_(False)),
        FuelRequest.status == "receipt_submitted",
    )


def _serialize(req: FuelRequest, db: Session | None = None) -> dict:
    chain_info = (
        describe_chain(
            db,
            req.approval_chain,
            req.approval_step,
            req.approval_log,
            not req.awaiting_approval,
        )
        if db is not None and req.approval_chain
        else {"approval_steps": [], "approval_log": load_json_list(req.approval_log)}
    )
    return {
        "id": req.id,
        "status": req.status,
        "driver_name": display_name(req.driver) if req.driver else None,
        "plate_number": req.plate_number,
        "city": req.city,
        "odo_photo_url": req.odo_photo_url,
        "odometer_reading": req.odometer_reading,
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
        # Org chart approval progress (empty when there's no chain).
        "awaiting_approval": bool(req.awaiting_approval),
        "can_act": getattr(req, "_can_act", True),
        "viewer_away": getattr(req, "_away", None),
        **chain_info,
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
    # Odometer reading in km (typed; the photo is the proof).
    odometer_reading: int | None = Form(None),
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
    if odometer_reading is not None and not 0 <= odometer_reading <= 9_999_999:
        raise HTTPException(status_code=400, detail="Enter a valid odometer reading.")

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

    # Org chart: every head above the driver with Fuel Request ticked,
    # in order. None -> straight to the coordinator, as before.
    employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
        if current_user.employee_id
        else None
    )
    chain = resolve_chain(db, employee, current_user, "fuel_request")

    req = FuelRequest(
        user_id=current_user.id,
        employee_id=current_user.employee_id,
        plate_number=plate_number,
        city=city,
        odo_photo_url="",
        odometer_reading=odometer_reading,
        status="pending",
        approval_chain=dump_chain(chain),
        approval_step=0,
        awaiting_approval=bool(chain),
    )
    db.add(req)
    db.flush()
    req.odo_photo_url = FileService().upload(odo_photo, f"fuel_requests/{req.id}/odo")
    db.commit()

    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


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
    return [_serialize(r, db) for r in rows]


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

    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


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
        q = q.filter(_needs_action_filter())
    elif status == "awaiting_approval":
        q = q.filter(FuelRequest.status == "pending", FuelRequest.awaiting_approval.is_(True))
    elif status:
        q = q.filter(FuelRequest.status == status)
    rows = q.order_by(FuelRequest.created_at.desc()).limit(300).all()
    return [_serialize(r, db) for r in rows]


@router.get("/alerts")
def fuel_request_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    """For the web bell: requests waiting for a fuel code or a receipt
    check, oldest first."""
    rows = (
        _query(db)
        .filter(_needs_action_filter())
        .order_by(FuelRequest.updated_at.asc())
        .all()
    )
    return [_serialize(r, db) for r in rows]


# =====================================================================
# ORG CHART HEADS -- approve / reject before the fuel code
# =====================================================================
def _is_superadmin(user: User) -> bool:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return role == "superadmin"


@router.get("/for-my-approval")
def list_fuel_for_my_approval(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fuel requests whose turn is with me on the Org Chart chain (or
    passed up past me because I'm away today -- read-only). Superadmin
    sees every request still awaiting approval."""
    rows = (
        _query(db)
        .filter(FuelRequest.status == "pending", FuelRequest.awaiting_approval.is_(True))
        .order_by(FuelRequest.created_at.asc())
        .all()
    )
    if _is_superadmin(current_user):
        return [_serialize(r, db) for r in rows]

    team = team_scope(db, current_user)
    mine = []
    for req in rows:
        if team is not None and req.employee_id not in team["employee_ids"]:
            continue
        chain = [int(i) for i in load_json_list(req.approval_chain)]
        if acting_index(db, chain, req.approval_step, current_user.id)[0] is not None:
            req._can_act = True
            mine.append(req)
        else:
            away = skipped_for(db, chain, req.approval_step, current_user.id)
            if away:
                req._can_act = False
                req._away = away
                mine.append(req)
    return [_serialize(r, db) for r in mine]


def _approval_turn(db: Session, req: FuelRequest, current_user: User):
    """(chain, acting step or None, skipped). The head whose turn it is
    acts on their step; a superadmin may act at any point."""
    if req.status != "pending" or not req.awaiting_approval:
        raise HTTPException(status_code=400, detail="This request isn't waiting for approval.")
    chain = [int(i) for i in load_json_list(req.approval_chain)]
    acting, skipped = acting_index(db, chain, req.approval_step, current_user.id)
    if acting is None and not _is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="It isn't your turn to approve this request.")
    return chain, acting, skipped


@router.post("/{request_id}/approve")
def approve_fuel_request(
    request_id: int,
    remarks: str | None = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_locked(db, request_id)
    chain, acting, skipped = _approval_turn(db, req, current_user)
    req.approval_log = log_skipped(db, req.approval_log, chain, skipped)
    req.approval_log = append_log(req.approval_log, current_user, "approved", remarks)

    if acting is not None and acting < len(chain) - 1:
        # Pass it to the next head up.
        req.approval_step = acting + 1
    else:
        # Last head (or a superadmin): over to the coordinator for the code.
        req.approval_step = len(chain)
        req.awaiting_approval = False
    db.commit()
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


@router.post("/{request_id}/reject")
def reject_fuel_request(
    request_id: int,
    reason: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_locked(db, request_id)
    chain, _acting, skipped = _approval_turn(db, req, current_user)
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required.")
    req.approval_log = log_skipped(db, req.approval_log, chain, skipped)
    req.approval_log = append_log(req.approval_log, current_user, "rejected", reason)
    req.status = "declined"
    req.note = reason
    req.awaiting_approval = False
    db.commit()
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


@router.get("/{request_id}")
def get_fuel_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_coordinator),
):
    req = _query(db).filter(FuelRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Fuel request not found.")
    return _serialize(req, db)


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
    if req.awaiting_approval:
        raise HTTPException(
            status_code=400,
            detail="This request is still waiting for Org Chart approval.",
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
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


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
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


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
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)


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
    return _serialize(_query(db).filter(FuelRequest.id == req.id).first(), db)
