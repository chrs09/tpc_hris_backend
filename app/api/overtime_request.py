from datetime import datetime, date, time as time_cls, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload, object_session

from app.services.payroll_lock import ensure_unlocked
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.employees import Employee
from app.models.overtime_request import OvertimeRequest
from app.models.attendance import AttendanceRecord
from app.models.overtime_approvals import OvertimeApproval
from app.utils.user_display import display_name
from app.services.approval_chain import (
    acting_index,
    skipped_for,
    log_skipped,
    team_scope,
    append_log,
    describe_chain,
    dump_chain,
    load_json_list,
    resolve_chain,
)
from app.schemas.overtime_request import OvertimeReviewAction
from app.services.file_service import FileService
from app.services.trip_payroll_service import now_ph, to_ph

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


# =========================================================
# LATE FILING -- forgot to clock in/out
#
# Allowed for any day in the employee's CURRENT payroll cutoff (their
# department's rule on the Payroll Cutoffs page) up to today, as long as Payroll hasn't already
# approved that employee's overtime for the cutoff. No selfie/GPS (they
# can't be captured after the fact); instead the request is flagged
# "Late filing" and approvers see the attendance time out next to it.
# =========================================================
MAX_OT_HOURS = 16


def _filing_window(db: Session, employee, today: date) -> tuple[date, date]:
    """Overtime can be filed for any day of the employee's CURRENT payroll
    cutoff up to today -- Motorpool its week, Admin its semi-monthly
    cutoff (Payroll Cutoffs page rules)."""
    from app.services.payroll_cutoffs import employee_cutoff

    start, end = employee_cutoff(db, employee, today)
    return start, end


def _cutoff_label(start: date, end: date) -> str:
    return f"{start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}"


def _attendance_on(db: Session, employee_id: int | None, on_date: date):
    if not employee_id:
        return None
    return (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.attendance_date == on_date,
        )
        .first()
    )


def _ph_hhmm(value: datetime | None) -> str | None:
    return to_ph(value).strftime("%H:%M") if value else None


def _payroll_approved(db: Session, employee_id: int | None, on_date: date) -> bool:
    if not employee_id:
        return False
    return (
        db.query(OvertimeApproval.id)
        .filter(
            OvertimeApproval.employee_id == employee_id,
            OvertimeApproval.cutoff_start <= on_date,
            OvertimeApproval.cutoff_end >= on_date,
            OvertimeApproval.status == "Approved",
        )
        .first()
        is not None
    )


def _parse_hhmm(value: str, label: str) -> time_cls:
    try:
        return datetime.strptime((value or "").strip(), "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label} must be a time like 17:30.")


def _span(ot_date: date, time_in: time_cls, time_out: time_cls) -> tuple[datetime, datetime]:
    start = datetime.combine(ot_date, time_in)
    end = datetime.combine(ot_date, time_out)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def _check_late_window(db: Session, employee_id: int | None, ot_date: date):
    ensure_unlocked(db, employee_id, ot_date, "overtime")
    today = now_ph().date()
    employee = db.query(Employee).filter(Employee.id == employee_id).first() if employee_id else None
    start, end = _filing_window(db, employee, today)
    if not (start <= ot_date <= today):
        raise HTTPException(
            status_code=400,
            detail=(
                "Missed overtime can only be filed for this payroll cutoff "
                f"({_cutoff_label(start, end)}), up to today."
            ),
        )
    if _payroll_approved(db, employee_id, ot_date):
        raise HTTPException(
            status_code=400,
            detail="Payroll has already approved overtime for this cutoff.",
        )


def _check_end_time(db: Session, employee_id, ot_date: date, end: datetime):
    """The claimed end can't be in the future. Ending after the
    attendance time out is allowed -- a call-back (went home, called back
    in) -- and is flagged to approvers instead (see _after_attendance)."""
    now = now_ph().replace(tzinfo=None)
    if end > now:
        raise HTTPException(status_code=400, detail="The time out can't be in the future.")


def _after_attendance(req: OvertimeRequest, attendance) -> bool:
    """Overtime that ends (or, still open, started) after the attendance
    time out that day -- a call-back the approver should confirm."""
    if not attendance or not attendance.check_out_time or not req.time_in:
        return False
    attendance_out = to_ph(attendance.check_out_time)
    if req.time_out is not None:
        _, point = _span(req.ot_date, req.time_in, req.time_out)
    else:
        point = datetime.combine(req.ot_date, req.time_in)
    return point > attendance_out + timedelta(minutes=GRACE_MINUTES)


def _approver_for(db: Session, employee: Employee, user: User):
    # Org Chart is the only source of approvers. Nobody above them ticks
    # Overtime -> a superadmin reviews it (same as cash advance).
    chain = resolve_chain(db, employee, user, "overtime")
    if chain:
        return chain, chain[0]
    superadmin = db.query(User).filter(User.role == "superadmin").first()
    if not superadmin:
        raise HTTPException(
            status_code=400,
            detail=(
                "No one has been set to approve your overtime yet. Ask an "
                "admin to tick Overtime for your head on the Org Chart."
            ),
        )
    return chain, superadmin.id


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
    session = object_session(req)
    attendance = (
        _attendance_on(session, req.employee_id, req.ot_date) if session else None
    )
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
        # Who gave the final approval / rejection (full name).
        "approved_by_name": (
            display_name(req.approved_by) if req.approved_by else None
        ),
        "approved_at": req.approved_at,
        "created_at": req.created_at,
        # The head can see this request from the moment it's filed, but
        # can only actually approve/reject it once the employee has
        # clocked out (time_out is set).
        "can_approve": req.time_out is not None,
        "filed_late": bool(req.filed_late),
        "manual_time_out": bool(req.manual_time_out),
        "late_note": req.late_note,
        # What attendance recorded that day, to check the claimed hours,
        # and whether the overtime runs past it (call-back).
        "attendance_time_out": _ph_hhmm(
            attendance.check_out_time if attendance else None
        ),
        "after_attendance_time_out": _after_attendance(req, attendance),
        # Filed before the overtime was over (a plan): a later attendance
        # mismatch means they left early, not a call-back.
        "filed_in_advance": bool(
            req.filed_via_form
            and req.created_at
            and req.time_in
            and req.time_out
            and to_ph(req.created_at) < _span(req.ot_date, req.time_in, req.time_out)[1]
        ),
        # False when the viewer's step was passed up because they're
        # absent / on leave today (see for-my-approval).
        "can_act": getattr(req, "_can_act", True),
        "viewer_away": getattr(req, "_away", None),
        # Org chart approval progress (empty when routed the old way).
        **describe_chain(
            object_session(req),
            req.approval_chain,
            req.approval_step,
            req.approval_log,
            req.status != "pending",
        ),
    }


def _can_review(request: OvertimeRequest, current_user: User, db: Session) -> bool:
    """Org Chart chain: the approver whose turn it is. Requests filed
    without a chain: whoever was set as approver when filed. A superadmin
    can always review (as with every other approval type)."""
    role = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
    if role == "superadmin":
        return True
    if not request.approval_chain and request.requested_by_user_id == current_user.id:
        return True

    if request.approval_chain:
        # Org chart routing: only the approver whose turn it is -- passed
        # up the chain while that approver is absent / on leave today.
        chain = [int(i) for i in load_json_list(request.approval_chain)]
        return acting_index(db, chain, request.approval_step, current_user.id)[0] is not None

    return False


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
        # Started on an earlier day = probably forgot to clock out; the
        # app offers "Enter time out" (POST /{id}/finish) for it.
        attendance = _attendance_on(db, ongoing.employee_id, ongoing.ot_date)
        return {
            "state": "ongoing",
            "request": _serialize(ongoing),
            "started_earlier_day": ongoing.ot_date < now.date(),
            "suggested_time_out": _ph_hhmm(
                attendance.check_out_time if attendance else None
            ),
        }

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
    # Overtime is filed now (POST /file) -- no more clock in/out. Kept so
    # an old app version gets a clear message instead of a 404.
    raise HTTPException(
        status_code=400,
        detail=(
            "Overtime clock in was replaced by overtime filing. Update the "
            "app, then tap File Overtime."
        ),
    )


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


@router.get("/file/options")
def get_overtime_filing_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The days overtime can be filed for -- every day of the current
    payroll cutoff up to today (today may be filed before or after working
    it), newest first, each pre-filled: start = scheduled time out, end =
    attendance time out when it's later than that."""
    today = now_ph().date()

    employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
    )

    cutoff_start, cutoff_end = _filing_window(db, employee, today)
    window = [
        today - timedelta(days=offset)
        for offset in range((today - cutoff_start).days + 1)
    ]

    days = []
    for day in window:
        attendance = _attendance_on(db, current_user.employee_id, day)
        scheduled_out = _get_scheduled_time_out(employee, day)
        attendance_out = attendance.check_out_time if attendance else None
        suggested_out = None
        if attendance_out and scheduled_out:
            out_ph = to_ph(attendance_out)
            if out_ph.replace(tzinfo=None) > datetime.combine(day, scheduled_out):
                suggested_out = out_ph.strftime("%H:%M")
        days.append(
            {
                "date": str(day),
                "label": day.strftime("%a, %b %d"),
                "has_attendance": bool(attendance and attendance.check_in_time),
                "attendance_time_in": _ph_hhmm(attendance.check_in_time if attendance else None),
                "attendance_time_out": _ph_hhmm(attendance_out),
                "scheduled_time_out": scheduled_out.strftime("%H:%M") if scheduled_out else None,
                "suggested_time_in": scheduled_out.strftime("%H:%M") if scheduled_out else None,
                "suggested_time_out": suggested_out,
                "is_today": day == today,
                "is_yesterday": day == today - timedelta(days=1),
                # Past days need attendance; today may be filed ahead.
                "can_file": (
                    not _payroll_approved(db, current_user.employee_id, day)
                    and (day == today or bool(attendance and attendance.check_in_time))
                ),
                "payroll_approved": _payroll_approved(db, current_user.employee_id, day),
            }
        )

    return {
        "days": days,
        "cutoff_start": str(cutoff_start),
        "cutoff_end": str(cutoff_end),
        "cutoff_label": _cutoff_label(cutoff_start, cutoff_end),
    }


@router.post("/file")
def file_overtime(
    ot_date: date = Form(...),
    time_in: str = Form(...),
    time_out: str = Form(...),
    reason: str = Form(...),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """File overtime for any day of the current payroll cutoff up to today
    (today: before extending work -- a plan -- or after). The only way
    overtime is filed; there's no clock in/out."""
    if current_user.role == "superadmin":
        raise HTTPException(
            status_code=403, detail="Superadmin accounts cannot file overtime requests."
        )
    if not reason.strip():
        raise HTTPException(status_code=400, detail="Reason is required.")

    employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
    )
    if not employee:
        raise HTTPException(status_code=400, detail="Your account isn't linked to an employee.")

    today = now_ph().date()
    cutoff_start, cutoff_end = _filing_window(db, employee, today)
    if not (cutoff_start <= ot_date <= today):
        raise HTTPException(
            status_code=400,
            detail=(
                "Overtime can only be filed for this payroll cutoff "
                f"({_cutoff_label(cutoff_start, cutoff_end)}), up to today."
            ),
        )
    ensure_unlocked(db, employee.id, ot_date, "overtime")
    if _payroll_approved(db, employee.id, ot_date):
        raise HTTPException(
            status_code=400,
            detail="Payroll has already approved overtime for this cutoff.",
        )

    attendance = _attendance_on(db, employee.id, ot_date)
    if ot_date < today and (not attendance or not attendance.check_in_time):
        raise HTTPException(
            status_code=400,
            detail=(
                f"You have no attendance on {ot_date:%b %d}, so overtime can't be "
                "filed for it."
            ),
        )

    start_t = _parse_hhmm(time_in, "Start")
    end_t = _parse_hhmm(time_out, "End")
    start, end = _span(ot_date, start_t, end_t)
    hours = round((end - start).total_seconds() / 3600, 2)
    if hours > MAX_OT_HOURS:
        raise HTTPException(status_code=400, detail=f"That's more than {MAX_OT_HOURS} hours.")
    # A future end is fine -- filing before the overtime is worked.

    # No overlap with other overtime that day.
    for other in db.query(OvertimeRequest).filter(
        OvertimeRequest.user_id == current_user.id,
        OvertimeRequest.ot_date == ot_date,
        OvertimeRequest.status.in_(["pending", "approved"]),
    ):
        if other.time_out is None:
            raise HTTPException(
                status_code=400,
                detail="You have an overtime from that day that isn't clocked out yet -- enter its time out instead.",
            )
        o_start, o_end = _span(other.ot_date, other.time_in, other.time_out)
        if o_start < end and start < o_end:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"This overlaps your overtime {other.time_in.strftime('%H:%M')}-"
                    f"{other.time_out.strftime('%H:%M')} that day."
                ),
            )

    chain, requested_by = _approver_for(db, employee, current_user)

    request = OvertimeRequest(
        user_id=current_user.id,
        employee_id=employee.id,
        requested_by_user_id=requested_by,
        approval_chain=dump_chain(chain),
        approval_step=0,
        ot_date=ot_date,
        time_in=start_t,
        time_out=end_t,
        computed_hours=hours,
        reason=reason.strip(),
        status="pending",
        # Filed after the day (forgot to file on the day).
        filed_late=ot_date < today,
        filed_via_form=True,
    )
    db.add(request)
    db.flush()

    if photo is not None and getattr(photo, "filename", None):
        if not (photo.content_type or "").startswith("image/"):
            raise HTTPException(status_code=400, detail="Photo must be an image file.")
        request.selfie_photo_url = FileService().upload(
            photo, f"overtime/{request.id}/proof"
        )

    db.commit()
    db.refresh(request)
    return _serialize(request)


@router.post("/{request_id}/finish")
def finish_forgotten_overtime(
    request_id: int,
    time_out: str = Form(...),
    note: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clocked in but forgot to clock out: enter the real end time. The
    request stays with its approvers, flagged as a typed-in time out."""
    request = (
        db.query(OvertimeRequest).filter(OvertimeRequest.id == request_id).first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Overtime request not found")
    if request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only finish your own overtime.")
    if request.time_out is not None:
        raise HTTPException(status_code=400, detail="Already clocked out.")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="This request is no longer active.")
    if not note.strip():
        raise HTTPException(status_code=400, detail="Say briefly what happened.")

    _check_late_window(db, request.employee_id, request.ot_date)

    end_t = _parse_hhmm(time_out, "Time out")
    start, end = _span(request.ot_date, request.time_in, end_t)
    hours = round((end - start).total_seconds() / 3600, 2)
    if hours > MAX_OT_HOURS:
        raise HTTPException(status_code=400, detail=f"That's more than {MAX_OT_HOURS} hours.")
    _check_end_time(db, request.employee_id, request.ot_date, end)

    request.time_out = end_t
    request.computed_hours = hours
    request.manual_time_out = True
    request.late_note = note.strip()

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


@router.get("/approved")
def get_approved_overtime_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every head-approved overtime request, listed plainly (employee_id,
    ot_date, approved_hours) -- Payroll sums whichever of these fall
    inside its own cutoff period (cutoffs are computed on the frontend,
    not known here) to pre-fill its existing OT approval step, the same
    way it already consumes /overtime-approval/list."""
    rows = (
        db.query(OvertimeRequest)
        .filter(
            OvertimeRequest.status == "approved",
            OvertimeRequest.employee_id.isnot(None),
        )
        .order_by(OvertimeRequest.ot_date.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "employee_id": r.employee_id,
            "ot_date": str(r.ot_date),
            "approved_hours": r.approved_hours or 0,
        }
        for r in rows
    ]


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
    mine = []
    for r in pending:
        if _can_review(r, current_user, db):
            r._can_act = True
            mine.append(r)
        elif r.approval_chain:
            # Their step was passed up because they're out today: shown,
            # but they can't approve / reject it.
            away = skipped_for(
                db, [int(i) for i in load_json_list(r.approval_chain)], r.approval_step, current_user.id
            )
            if away:
                r._can_act = False
                r._away = away
                mine.append(r)
    # An org chart head only sees their own team's overtime.
    team = team_scope(db, current_user)
    if team is not None:
        mine = [r for r in mine if r.employee_id in team["employee_ids"]]
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
    ensure_unlocked(db, request.employee_id, request.ot_date, "overtime")
    if request.time_out is None:
        raise HTTPException(
            status_code=400,
            detail="This employee hasn't clocked out of overtime yet.",
        )
    if not _can_review(request, current_user, db):
        raise HTTPException(
            status_code=403, detail="You are not authorized to approve this request."
        )

    request.approved_hours = (
        payload.approved_hours
        if payload.approved_hours is not None
        # Keep what an earlier head in the chain approved, if any.
        else request.approved_hours
        if request.approved_hours is not None
        else request.computed_hours
    )
    chain = [int(i) for i in load_json_list(request.approval_chain)]
    acting, skipped = (
        acting_index(db, chain, request.approval_step, current_user.id)
        if chain
        else (None, [])
    )
    # Approvers before this one who are out today were skipped.
    request.approval_log = log_skipped(db, request.approval_log, chain, skipped)
    request.approval_log = append_log(
        request.approval_log,
        current_user,
        "approved",
        payload.remarks,
        approved_hours=request.approved_hours,
    )

    # Org chart chain: pass it to the next head up.
    if chain and acting is not None and acting < len(chain) - 1:
        request.approval_step = acting + 1
        request.requested_by_user_id = chain[request.approval_step]
        db.commit()
        db.refresh(request)
        return _serialize(request)

    if chain and acting is not None:
        request.approval_step = acting
    request.status = "approved"
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
    ensure_unlocked(db, request.employee_id, request.ot_date, "overtime")
    if not _can_review(request, current_user, db):
        raise HTTPException(
            status_code=403, detail="You are not authorized to reject this request."
        )

    request.approval_log = append_log(
        request.approval_log, current_user, "rejected", payload.remarks
    )
    request.status = "rejected"
    request.remarks = payload.remarks
    request.approved_by_user_id = current_user.id
    request.approved_at = datetime.utcnow()

    db.commit()
    db.refresh(request)
    return _serialize(request)
