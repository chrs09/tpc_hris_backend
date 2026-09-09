from datetime import datetime, date, time as time_cls, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.employees import Employee
from app.models.overtime_request import OvertimeRequest
from app.models.department_head import DepartmentHead
from app.schemas.overtime_request import OvertimeReviewAction
from app.services.file_service import FileService
from app.services.trip_payroll_service import now_ph
from app.api.attendance import find_nearest_allowed_attendance_location

router = APIRouter(prefix="/overtime-requests", tags=["Overtime Requests"])

# How long after the employee's scheduled time-out the "Overtime In" action
# becomes available -- they need to actually still be there past their
# shift, not just about to leave.
GRACE_MINUTES = 5


def _compute_hours(ot_date: date, time_in: time_cls, time_out: time_cls) -> float:
    """Hours between time_in and time_out on ot_date. If time_out is not
    after time_in (e.g. 8pm-12:30am), the shift is treated as crossing
    into the next day."""
    start = datetime.combine(ot_date, time_in)
    end = datetime.combine(ot_date, time_out)
    if end <= start:
        end += timedelta(days=1)
    return round((end - start).total_seconds() / 3600, 2)


def _get_department_head(employee: Employee | None, db: Session) -> int | None:
    if not employee or not employee.department:
        return None
    head_entry = (
        db.query(DepartmentHead)
        .filter(DepartmentHead.department == employee.department)
        .first()
    )
    return head_entry.head_user_id if head_entry else None


def _get_scheduled_time_out(employee: Employee | None, on_date: date) -> time_cls | None:
    """The employee's assigned schedule_template's time-out for the given
    date's weekday, or None if they have no schedule (or no template)."""
    if not employee or not employee.schedule_template:
        return None
    day_name = on_date.strftime("%A").lower()
    return getattr(employee.schedule_template, f"{day_name}_out", None)


def _get_ongoing_request(employee_id: int | None, user_id: int, db: Session):
    return (
        db.query(OvertimeRequest)
        .filter(
            OvertimeRequest.user_id == user_id,
            OvertimeRequest.time_out.is_(None),
            OvertimeRequest.status == "pending",
        )
        .order_by(OvertimeRequest.created_at.desc())
        .first()
    )


def _serialize(req: OvertimeRequest) -> dict:
    employee = req.employee
    requester = req.requester
    approver = req.requested_by
    return {
        "id": req.id,
        "employee_id": req.employee_id,
        "employee_name": (
            f"{employee.first_name} {employee.last_name}"
            if employee
            else (requester.username if requester else None)
        ),
        "ot_date": str(req.ot_date),
        "time_in": req.time_in.strftime("%H:%M") if req.time_in else None,
        "time_out": req.time_out.strftime("%H:%M") if req.time_out else None,
        "computed_hours": req.computed_hours,
        "reason": req.reason,
        "selfie_photo_url": req.selfie_photo_url,
        "clock_in_lat": req.clock_in_lat,
        "clock_in_long": req.clock_in_long,
        "clock_out_lat": req.clock_out_lat,
        "clock_out_long": req.clock_out_long,
        "status": req.status,
        "approved_hours": req.approved_hours,
        "remarks": req.remarks,
        "requested_by_user_id": req.requested_by_user_id,
        "requested_by_name": approver.username if approver else None,
        "approved_by_user_id": req.approved_by_user_id,
        "approved_at": req.approved_at,
        "created_at": req.created_at,
        # The head can see this request from the moment it's filed, but
        # can only actually approve/reject it once the employee has
        # clocked out (time_out is set).
        "can_approve": req.time_out is not None,
    }


def _can_review(request: OvertimeRequest, current_user: User, db: Session) -> bool:
    """A request can be reviewed by whoever was picked as "requested by"
    when it was filed, OR by the requester's department's immediate head
    (see the Reporting Hierarchy / DepartmentHead page) -- whichever
    applies, since either one may be the actual person who called the
    employee in for overtime."""
    if request.requested_by_user_id == current_user.id:
        return True

    employee = request.employee
    if not employee or not employee.department:
        return False

    head_entry = (
        db.query(DepartmentHead)
        .filter(DepartmentHead.department == employee.department)
        .first()
    )
    return bool(head_entry and head_entry.head_user_id == current_user.id)


@router.get("/eligibility")
def get_overtime_eligibility(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tells the employee dashboard whether to show "Overtime In" (not yet
    eligible / eligible) or "Overtime Out" (already clocked in)."""
    now = now_ph()

    ongoing = _get_ongoing_request(current_user.employee_id, current_user.id, db)
    if ongoing:
        return {"state": "ongoing", "request": _serialize(ongoing)}

    employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
    )
    scheduled_out = _get_scheduled_time_out(employee, now.date())

    if not scheduled_out:
        return {"state": "no_schedule", "server_time": now.strftime("%H:%M")}

    eligible_at = datetime.combine(now.date(), scheduled_out) + timedelta(
        minutes=GRACE_MINUTES
    )

    is_eligible = now >= eligible_at

    return {
        "state": "eligible" if is_eligible else "not_yet",
        "scheduled_time_out": scheduled_out.strftime("%H:%M"),
        "eligible_at": eligible_at.strftime("%H:%M"),
        "server_time": now.strftime("%H:%M"),
    }


@router.post("/clock-in")
def clock_in_overtime(
    reason: str = Form(...),
    photo: UploadFile = File(...),
    lat: float | None = Form(None),
    long: float | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Superadmin accounts cannot file overtime requests.",
        )

    if not reason.strip():
        raise HTTPException(status_code=400, detail="Reason is required.")

    if _get_ongoing_request(current_user.employee_id, current_user.id, db):
        raise HTTPException(
            status_code=400,
            detail="You already have an overtime in progress. Clock out first.",
        )

    employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
    )
    if not employee or not employee.department:
        raise HTTPException(
            status_code=400,
            detail="Your account isn't linked to an employee department.",
        )

    requested_by_user_id = _get_department_head(employee, db)
    if not requested_by_user_id:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No immediate head has been set for the {employee.department} "
                "department yet. Ask an admin to set this up in Reporting Hierarchy."
            ),
        )

    now = now_ph()
    scheduled_out = _get_scheduled_time_out(employee, now.date())

    if not scheduled_out:
        raise HTTPException(
            status_code=400,
            detail="You don't have an assigned schedule for today.",
        )

    eligible_at = datetime.combine(now.date(), scheduled_out) + timedelta(
        minutes=GRACE_MINUTES
    )
    if now < eligible_at:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Overtime can only be started {GRACE_MINUTES} minutes after "
                f"your scheduled time-out ({scheduled_out.strftime('%H:%M')})."
            ),
        )

    request = OvertimeRequest(
        user_id=current_user.id,
        employee_id=current_user.employee_id,
        requested_by_user_id=requested_by_user_id,
        ot_date=now.date(),
        time_in=now.time(),
        reason=reason.strip(),
        status="pending",
        clock_in_lat=lat,
        clock_in_long=long,
    )
    db.add(request)
    db.flush()

    # Geofence is recorded on the selfie's watermark for a visual record,
    # but isn't enforced here -- unlike trips, an employee isn't blocked
    # from clocking in overtime just because they're away from a known
    # office location.
    geofence_label = None
    if lat is not None and long is not None:
        location, distance, is_allowed = find_nearest_allowed_attendance_location(
            lat, long
        )
        coords_text = f"{lat:.5f}, {long:.5f}"
        if location:
            geofence_label = f"{location['name']} ({int(distance)}m) · {coords_text}"
            if not is_allowed:
                geofence_label += " - outside geofence"
        else:
            geofence_label = coords_text

    file_service = FileService()
    request.selfie_photo_url = file_service.upload_overtime_selfie(
        photo, request.id, geofence_label=geofence_label
    )

    db.commit()
    db.refresh(request)

    return _serialize(request)


@router.post("/{request_id}/clock-out")
def clock_out_overtime(
    request_id: int,
    lat: float | None = Form(None),
    long: float | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = (
        db.query(OvertimeRequest).filter(OvertimeRequest.id == request_id).first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Overtime request not found")
    if request.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You can only clock out your own overtime."
        )
    if request.time_out is not None:
        raise HTTPException(status_code=400, detail="Already clocked out.")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="This request is no longer active.")

    now = now_ph()
    request.time_out = now.time()
    request.computed_hours = _compute_hours(request.ot_date, request.time_in, now.time())
    request.clock_out_lat = lat
    request.clock_out_long = long

    db.commit()
    db.refresh(request)
    return _serialize(request)


@router.get("/mine")
def get_my_overtime_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    requests = (
        db.query(OvertimeRequest)
        .options(
            joinedload(OvertimeRequest.employee), joinedload(OvertimeRequest.requested_by)
        )
        .filter(OvertimeRequest.user_id == current_user.id)
        .order_by(OvertimeRequest.created_at.desc())
        .all()
    )
    return [_serialize(r) for r in requests]


@router.post("/{request_id}/cancel")
def cancel_overtime_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = (
        db.query(OvertimeRequest).filter(OvertimeRequest.id == request_id).first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Overtime request not found")
    if request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only cancel your own requests")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending requests can be cancelled")

    request.status = "cancelled"
    db.commit()
    db.refresh(request)
    return _serialize(request)


@router.get("/for-my-approval")
def get_requests_for_my_approval(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pending = (
        db.query(OvertimeRequest)
        .options(
            joinedload(OvertimeRequest.employee),
            joinedload(OvertimeRequest.requested_by),
        )
        .filter(OvertimeRequest.status == "pending")
        .order_by(OvertimeRequest.created_at.asc())
        .all()
    )
    mine = [r for r in pending if _can_review(r, current_user, db)]
    return [_serialize(r) for r in mine]


@router.post("/{request_id}/approve")
def approve_overtime_request(
    request_id: int,
    payload: OvertimeReviewAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = (
        db.query(OvertimeRequest)
        .options(joinedload(OvertimeRequest.employee))
        .filter(OvertimeRequest.id == request_id)
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Overtime request not found")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending requests can be approved")
    if request.time_out is None:
        raise HTTPException(
            status_code=400,
            detail="This employee hasn't clocked out of overtime yet.",
        )
    if not _can_review(request, current_user, db):
        raise HTTPException(
            status_code=403, detail="You are not authorized to approve this request."
        )

    request.status = "approved"
    request.approved_hours = (
        payload.approved_hours
        if payload.approved_hours is not None
        else request.computed_hours
    )
    request.remarks = payload.remarks
    request.approved_by_user_id = current_user.id
    request.approved_at = datetime.utcnow()

    db.commit()
    db.refresh(request)
    return _serialize(request)


@router.post("/{request_id}/reject")
def reject_overtime_request(
    request_id: int,
    payload: OvertimeReviewAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = (
        db.query(OvertimeRequest)
        .options(joinedload(OvertimeRequest.employee))
        .filter(OvertimeRequest.id == request_id)
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Overtime request not found")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending requests can be reviewed")
    if not _can_review(request, current_user, db):
        raise HTTPException(
            status_code=403, detail="You are not authorized to reject this request."
        )

    request.status = "rejected"
    request.remarks = payload.remarks
    request.approved_by_user_id = current_user.id
    request.approved_at = datetime.utcnow()

    db.commit()
    db.refresh(request)
    return _serialize(request)
