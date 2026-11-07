"""Missed time in (heads answer) and time corrections (employees file).

* /attendance-requests/missed-time-in -- AttendanceAlerts waiting on me
  (app/services/attendance_alerts.py): Late / 2nd half / Absent today;
  for an earlier day "Does this employee work on this day?" Yes / No.
* /attendance-requests/time-corrections -- an employee asks to set or fix
  their time in / out for a day (forgot to time in or out, wrong time).
  It goes to the Org Chart attendance approvers in turn; the last
  approval writes the times into the attendance record, every change in
  the attendance audit log. Admins approve the employee's request instead
  of typing over their times.
"""

from datetime import date, datetime, timedelta

import pytz
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.api.attendance import _ph_stamp, format_attendance_time_only, log_adjustment
from app.core.database import get_db
from app.core.dependencies import get_current_user, has_editable_grant
from app.models.attendance import AttendanceRecord
from app.models.attendance_alert import AttendanceAlert
from app.models.employees import Employee
from app.models.time_correction import TimeCorrectionRequest
from app.models.user import User
from app.services.approval_chain import (
    acting_index,
    append_log,
    describe_chain,
    dump_chain,
    effective_step,
    load_json_list,
    log_skipped,
    resolve_chain,
    team_scope,
)
from app.services.attendance_alerts import (
    email_employee_to_correct,
    is_trip_based,
    now_ph,
)
from app.services.payroll_lock import ensure_unlocked
from app.utils.user_display import display_name

router = APIRouter(prefix="/attendance-requests", tags=["Attendance Requests"])

PH_TZ = pytz.timezone("Asia/Manila")
UTC = pytz.utc
LOOKBACK_DAYS = 45
# Superadmin / Attendance grid "Can edit": sees and answers every one.
EDIT_GRANTS = ["hris.attendance_grid_view"]

DECISION_LABELS = {
    "late": "Late",
    "second_half": "2nd half",
    "absent": "Absent",
    "works": "Works this day",
    "timed_in": "Timed in",
    "corrected": "Time corrected",
}


def _name(employee: Employee | None, fallback_id=None) -> str:
    if not employee:
        return f"Employee #{fallback_id}"
    return f"{employee.first_name} {employee.last_name}".strip()


def _clock(value) -> str | None:
    return value.strftime("%I:%M %p").lstrip("0") if value else None


def _hhmm(value) -> str | None:
    """Stored UTC -> PH "HH:MM" (for time inputs)."""
    if not value:
        return None
    return UTC.localize(value).astimezone(PH_TZ).strftime("%H:%M")


def _record(db: Session, employee_id: int, day: date):
    return (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.attendance_date == day,
        )
        .first()
    )


# =====================================================================
# MISSED TIME IN -- heads
# =====================================================================
def _alert_payload(db: Session, alert: AttendanceAlert, user: User, sees_all: bool) -> dict:
    today = now_ph().date()
    employee = alert.employee
    # Past days (or a Late / 2nd half that never timed in) get the cutoff
    # question; today gets Late / 2nd half / Absent.
    stage = "today" if alert.attendance_date == today else "past"
    needs_answer = alert.status == "open" or (
        alert.status == "waiting_time_in" and stage == "past"
    )
    head = alert.head
    return {
        "id": alert.id,
        "employee_id": alert.employee_id,
        "employee_name": _name(employee, alert.employee_id),
        "position": employee.position if employee else None,
        "department": employee.department if employee else None,
        "attendance_date": str(alert.attendance_date),
        "date_label": alert.attendance_date.strftime("%a, %b %d"),
        "scheduled_in": _clock(alert.scheduled_in),
        "stage": stage,
        "status": alert.status,
        "decision": alert.decision,
        "decision_label": DECISION_LABELS.get(alert.decision),
        "reason": alert.reason,
        "decided_by": display_name(alert.decided_by) if alert.decided_by else None,
        "head_name": display_name(head) if head else None,
        "needs_answer": needs_answer,
        "can_act": needs_answer and (sees_all or alert.head_user_id == user.id),
    }


@router.get("/missed-time-in")
def missed_time_in_for_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Open alerts for me (my people), newest day first. Superadmin /
    Attendance grid "Can edit": every one (a head still only their team)."""
    since = now_ph().date() - timedelta(days=LOOKBACK_DAYS)
    sees_all = has_editable_grant(db, current_user, EDIT_GRANTS)
    query = (
        db.query(AttendanceAlert)
        .options(
            joinedload(AttendanceAlert.employee),
            joinedload(AttendanceAlert.head),
            joinedload(AttendanceAlert.decided_by),
        )
        .filter(
            AttendanceAlert.attendance_date >= since,
            AttendanceAlert.status.in_(("open", "waiting_time_in", "waiting_employee")),
        )
    )
    if not sees_all:
        query = query.filter(AttendanceAlert.head_user_id == current_user.id)
    alerts = query.order_by(AttendanceAlert.attendance_date.desc()).all()
    team = team_scope(db, current_user) if sees_all else None
    if team is not None:
        alerts = [
            a for a in alerts
            if a.employee_id in team["employee_ids"] or a.head_user_id == current_user.id
        ]
    return [_alert_payload(db, a, current_user, sees_all) for a in alerts]


class DecideIn(BaseModel):
    # today: late / second_half / absent; an earlier day: works / absent
    decision: str
    reason: str | None = None


@router.post("/missed-time-in/{alert_id}/decide")
def decide_missed_time_in(
    alert_id: int,
    payload: DecideIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = db.get(AttendanceAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Not found.")
    sees_all = has_editable_grant(db, current_user, EDIT_GRANTS)
    if alert.head_user_id != current_user.id and not sees_all:
        raise HTTPException(status_code=403, detail="This isn't yours to answer.")
    info = _alert_payload(db, alert, current_user, sees_all)
    if not info["needs_answer"]:
        raise HTTPException(status_code=400, detail="This is already answered.")

    decision = (payload.decision or "").strip()
    allowed = ("late", "second_half", "absent") if info["stage"] == "today" else ("works", "absent")
    if decision not in allowed:
        raise HTTPException(status_code=400, detail="Pick one of the options.")
    reason = (payload.reason or "").strip()
    if decision == "absent" and not reason:
        raise HTTPException(status_code=400, detail="Give the reason for marking Absent.")
    ensure_unlocked(db, alert.employee_id, alert.attendance_date, "attendance")

    record = _record(db, alert.employee_id, alert.attendance_date)
    if record and record.check_in_time:
        raise HTTPException(status_code=400, detail="They have timed in already.")

    alert.decision = decision
    alert.reason = reason or None
    alert.decided_by_user_id = current_user.id
    alert.decided_at = datetime.utcnow()
    message = "Saved."

    if decision == "absent":
        if not record:
            record = AttendanceRecord(
                employee_id=alert.employee_id,
                attendance_date=alert.attendance_date,
                status="Absent",
                attendance_method="MANUAL",
                created_by_user_id=current_user.id,
                remarks=reason,
            )
            db.add(record)
            db.flush()
            log_adjustment(
                db, record, "created", None, "Absent", current_user,
                f"Missed time in -- marked Absent: {reason}",
            )
        else:
            log_adjustment(
                db, record, "status", record.status, "Absent", current_user,
                f"Missed time in -- marked Absent: {reason}",
            )
            record.status = "Absent"
            record.remarks = record.remarks or reason
        alert.status = "closed"
        alert.closed_at = datetime.utcnow()
        message = "Marked Absent."
    elif decision == "works":
        alert.status = "waiting_employee"
        if email_employee_to_correct(db, alert):
            alert.employee_emailed_at = datetime.utcnow()
            message = "Saved -- the employee was emailed to file a time correction."
        else:
            message = (
                "Saved -- they'll see it on their dashboard (no email on file)."
            )
    else:
        alert.status = "waiting_time_in"
        message = (
            "Saved -- it becomes "
            f"{'Delay' if decision == 'late' else 'Halfday'} when they time in."
        )

    db.commit()
    return {"message": message, "id": alert.id, "status": alert.status}


@router.get("/my-alerts")
def my_missed_days(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Days my head confirmed I worked but I have no time in -- file a
    time correction for each."""
    if not current_user.employee_id:
        return []
    alerts = (
        db.query(AttendanceAlert)
        .filter(
            AttendanceAlert.employee_id == current_user.employee_id,
            AttendanceAlert.status == "waiting_employee",
        )
        .order_by(AttendanceAlert.attendance_date.asc())
        .all()
    )
    pending = {
        c.attendance_date
        for c in db.query(TimeCorrectionRequest.attendance_date).filter(
            TimeCorrectionRequest.employee_id == current_user.employee_id,
            TimeCorrectionRequest.status == "pending",
        )
    }
    return [
        {
            "id": a.id,
            "attendance_date": str(a.attendance_date),
            "date_label": a.attendance_date.strftime("%a, %b %d"),
            "scheduled_in": _clock(a.scheduled_in),
            "filed": a.attendance_date in pending,
        }
        for a in alerts
    ]


# =====================================================================
# TIME CORRECTIONS
# =====================================================================
def _at(day: date, hhmm: str | None) -> datetime | None:
    """"08:05" on that PH day -> naive UTC."""
    if not hhmm:
        return None
    try:
        clock = datetime.strptime(hhmm.strip(), "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Enter times as HH:MM.")
    return PH_TZ.localize(datetime.combine(day, clock)).astimezone(UTC).replace(tzinfo=None)


def _times(day: date, time_in: str | None, time_out: str | None, record) -> tuple:
    """The requested times (UTC). A time out earlier than the time in is
    the next morning (a night shift). Neither can be in the future."""
    start = _at(day, time_in)
    end = _at(day, time_out)
    if start is None and end is None:
        raise HTTPException(status_code=400, detail="Enter the time in, the time out, or both.")
    reference = start or (record.check_in_time if record else None)
    if end is not None and reference is not None and end <= reference:
        end += timedelta(days=1)
    now = datetime.utcnow()
    if (start and start > now) or (end and end > now):
        raise HTTPException(status_code=400, detail="A time can't be in the future.")
    return start, end


def _correction_payload(db: Session, c: TimeCorrectionRequest, user: User | None = None, sees_all=False) -> dict:
    record = _record(db, c.employee_id, c.attendance_date)
    progress = describe_chain(
        db, c.approval_chain, c.approval_step, c.approval_log, c.status != "pending"
    )
    current = progress.get("current_approver_id")
    return {
        "id": c.id,
        "employee_id": c.employee_id,
        "employee_name": _name(c.employee, c.employee_id),
        "position": c.employee.position if c.employee else None,
        "attendance_date": str(c.attendance_date),
        "date_label": c.attendance_date.strftime("%a, %b %d"),
        "time_in": format_attendance_time_only(c.time_in),
        "time_in_hhmm": _hhmm(c.time_in),
        "time_out": format_attendance_time_only(c.time_out),
        "time_out_hhmm": _hhmm(c.time_out),
        # What the attendance shows now (to compare).
        "current_time_in": format_attendance_time_only(record.check_in_time) if record else None,
        "current_time_out": format_attendance_time_only(record.check_out_time) if record else None,
        "current_status": record.status if record else None,
        "reason": c.reason,
        "time_in_photo_url": c.time_in_photo_url,
        "time_out_photo_url": c.time_out_photo_url,
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "decided_at": c.decided_at.isoformat() if c.decided_at else None,
        **progress,
        "my_turn": bool(user) and current == user.id,
        "can_act": bool(user) and c.status == "pending" and (current == user.id or sees_all),
    }


class CorrectionIn(BaseModel):
    attendance_date: date
    time_in: str | None = None  # "HH:MM", PH
    time_out: str | None = None
    reason: str


@router.get("/time-corrections/eligibility")
def time_correction_eligibility(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Whether this person files time corrections: anyone linked to an
    employee who times in / out -- any role, superadmin included -- but
    not drivers / helpers, whose attendance comes from their trips. The
    web dashboards and the app show Time Correction only when true."""
    employee = db.get(Employee, current_user.employee_id) if current_user.employee_id else None
    if not employee:
        return {"can_file": False, "reason": "Your login isn't linked to an employee."}
    if is_trip_based(employee, current_user):
        return {"can_file": False, "reason": "Your attendance comes from your trips."}
    return {"can_file": True, "reason": None}


@router.get("/time-corrections/mine")
def my_time_corrections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.employee_id:
        return []
    items = (
        db.query(TimeCorrectionRequest)
        .options(joinedload(TimeCorrectionRequest.employee))
        .filter(TimeCorrectionRequest.employee_id == current_user.employee_id)
        .order_by(TimeCorrectionRequest.attendance_date.desc(), TimeCorrectionRequest.id.desc())
        .limit(60)
        .all()
    )
    return [_correction_payload(db, c) for c in items]


@router.post("/time-corrections")
def file_time_correction(
    payload: CorrectionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = db.get(Employee, current_user.employee_id) if current_user.employee_id else None
    if not employee:
        raise HTTPException(status_code=400, detail="Your login isn't linked to an employee.")
    if is_trip_based(employee, current_user):
        raise HTTPException(
            status_code=400,
            detail="Driver and helper attendance comes from trips -- ask your coordinator.",
        )
    day = payload.attendance_date
    if day > now_ph().date():
        raise HTTPException(status_code=400, detail="Pick today or an earlier day.")
    if day < now_ph().date() - timedelta(days=LOOKBACK_DAYS):
        raise HTTPException(status_code=400, detail="That day is too far back -- ask HR.")
    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Say why the time needs correcting.")
    ensure_unlocked(db, employee.id, day, "attendance")
    if (
        db.query(TimeCorrectionRequest.id)
        .filter(
            TimeCorrectionRequest.employee_id == employee.id,
            TimeCorrectionRequest.attendance_date == day,
            TimeCorrectionRequest.status == "pending",
        )
        .first()
    ):
        raise HTTPException(
            status_code=400,
            detail="You already have a pending correction for that day -- cancel it to file again.",
        )
    record = _record(db, employee.id, day)
    start, end = _times(day, payload.time_in, payload.time_out, record)

    chain = resolve_chain(db, employee, current_user, "attendance")
    correction = TimeCorrectionRequest(
        employee_id=employee.id,
        attendance_date=day,
        time_in=start,
        time_out=end,
        reason=reason[:1000],
        status="pending",
        approval_chain=dump_chain(chain),
        approval_step=0,
        approval_log=append_log(None, current_user, "filed", reason[:300]),
        filed_by_user_id=current_user.id,
    )
    db.add(correction)
    db.commit()
    return {"message": "Time correction filed.", "id": correction.id}


@router.post("/time-corrections/{correction_id}/cancel")
def cancel_time_correction(
    correction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.get(TimeCorrectionRequest, correction_id)
    if not c or c.employee_id != current_user.employee_id:
        raise HTTPException(status_code=404, detail="Not found.")
    if c.status != "pending":
        raise HTTPException(status_code=400, detail="Only a pending request can be cancelled.")
    c.status = "cancelled"
    c.decided_at = datetime.utcnow()
    c.approval_log = append_log(c.approval_log, current_user, "cancelled")
    db.commit()
    return {"message": "Cancelled."}


@router.post("/time-corrections/{correction_id}/photos")
def upload_time_correction_photos(
    correction_id: int,
    time_in_photo: UploadFile | None = File(None),
    time_out_photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Proof for the time in and / or time out (photo or screenshot) --
    sent right after filing, while it's still pending. Shown to the
    approvers."""
    from app.services.file_service import FileService

    c = db.get(TimeCorrectionRequest, correction_id)
    if not c or c.employee_id != current_user.employee_id:
        raise HTTPException(status_code=404, detail="Not found.")
    if c.status != "pending":
        raise HTTPException(status_code=400, detail="Only a pending request can take photos.")
    uploads = [(f, field) for f, field in ((time_in_photo, "time_in"), (time_out_photo, "time_out")) if f and f.filename]
    if not uploads:
        raise HTTPException(status_code=400, detail="Attach a photo.")
    for upload, field in uploads:
        if not (upload.content_type or "").startswith("image/"):
            raise HTTPException(status_code=400, detail="Photos must be images.")
        url = FileService().upload(upload, f"time_corrections/{c.id}/{field}")
        setattr(c, f"{field}_photo_url", url)
    db.commit()
    return {
        "time_in_photo_url": c.time_in_photo_url,
        "time_out_photo_url": c.time_out_photo_url,
    }


def _current_approver(db: Session, c: TimeCorrectionRequest) -> int | None:
    chain = [int(i) for i in load_json_list(c.approval_chain)]
    if not chain:
        return None
    index, _ = effective_step(db, chain, c.approval_step or 0)
    return chain[index] if index < len(chain) else None


@router.get("/time-corrections/for-my-approval")
def time_corrections_for_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pending ones whose turn is mine -- or, for a superadmin /
    Attendance grid "Can edit", every pending one (a head: their team)."""
    sees_all = has_editable_grant(db, current_user, EDIT_GRANTS)
    items = (
        db.query(TimeCorrectionRequest)
        .options(joinedload(TimeCorrectionRequest.employee))
        .filter(TimeCorrectionRequest.status == "pending")
        .order_by(TimeCorrectionRequest.attendance_date.desc())
        .all()
    )
    team = team_scope(db, current_user) if sees_all else None
    result = []
    for c in items:
        mine = _current_approver(db, c) == current_user.id
        if not mine and not sees_all:
            continue
        if not mine and team is not None and c.employee_id not in team["employee_ids"]:
            continue
        result.append(_correction_payload(db, c, current_user, sees_all))
    return result


class DecisionIn(BaseModel):
    remarks: str | None = None
    # The approver may fix the requested times ("HH:MM").
    time_in: str | None = None
    time_out: str | None = None


def _acting(db: Session, c: TimeCorrectionRequest, user: User):
    """(chain, acting index or None, skipped). Only the head whose turn it
    is -- or a superadmin / "Can edit" grant (who finishes it)."""
    if c.status != "pending":
        raise HTTPException(status_code=400, detail="This request is already decided.")
    if user.employee_id and user.employee_id == c.employee_id:
        raise HTTPException(
            status_code=403, detail="Someone else has to approve your own time correction."
        )
    chain = [int(i) for i in load_json_list(c.approval_chain)]
    acting, skipped = acting_index(db, chain, c.approval_step, user.id) if chain else (None, [])
    if acting is None and not has_editable_grant(db, user, EDIT_GRANTS):
        raise HTTPException(status_code=403, detail="It isn't your turn to approve this.")
    return chain, acting, skipped


def apply_correction(db: Session, c: TimeCorrectionRequest, user: User) -> None:
    """Writes the approved times into the attendance record (made if the
    day has none), each change in the audit log; closes that day's
    missed time in alert."""
    record = _record(db, c.employee_id, c.attendance_date)
    had_time_in = bool(record and record.check_in_time)
    if not record:
        record = AttendanceRecord(
            employee_id=c.employee_id,
            attendance_date=c.attendance_date,
            status="Present",
            attendance_method="CORRECTION",
            created_by_user_id=user.id,
        )
        db.add(record)
        db.flush()
        log_adjustment(db, record, "created", None, "Present", user, f"Time correction #{c.id}")
    note = f"Time correction #{c.id} approved: {c.reason}"
    for field, value in (("check_in_time", c.time_in), ("check_out_time", c.time_out)):
        if value is None:
            continue
        log_adjustment(db, record, field, _ph_stamp(getattr(record, field)), _ph_stamp(value), user, note)
        setattr(record, field, value)
    # A day with no attendance (marked Absent) that they did work.
    if not had_time_in and c.time_in is not None and record.status == "Absent" and not record.short_duty:
        log_adjustment(db, record, "status", "Absent", "Present", user, note)
        record.status = "Present"
    # A pending "forgot to time out" for the same day is settled by this.
    if c.time_out is not None and record.time_out_face_review_status == "MISSED_TIME_OUT":
        record.time_out_face_review_status = "APPROVED"
        record.time_out_face_review_reason = f"Settled by time correction #{c.id}."
    alert = (
        db.query(AttendanceAlert)
        .filter(
            AttendanceAlert.employee_id == c.employee_id,
            AttendanceAlert.attendance_date == c.attendance_date,
            AttendanceAlert.status != "closed",
        )
        .first()
    )
    if alert:
        alert.status = "closed"
        alert.decision = "corrected" if alert.decision in (None, "works") else alert.decision
        alert.closed_at = datetime.utcnow()


@router.post("/time-corrections/{correction_id}/approve")
def approve_time_correction(
    correction_id: int,
    payload: DecisionIn = Body(DecisionIn()),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.get(TimeCorrectionRequest, correction_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found.")
    chain, acting, skipped = _acting(db, c, current_user)
    ensure_unlocked(db, c.employee_id, c.attendance_date, "attendance")
    if payload.time_in or payload.time_out:
        record = _record(db, c.employee_id, c.attendance_date)
        start, end = _times(
            c.attendance_date,
            payload.time_in or _hhmm(c.time_in),
            payload.time_out or _hhmm(c.time_out),
            record,
        )
        c.time_in, c.time_out = start, end

    remarks = (payload.remarks or "").strip() or None
    c.approval_log = log_skipped(db, c.approval_log, chain, skipped)
    c.approval_log = append_log(c.approval_log, current_user, "approved", remarks)
    passes_up = acting is not None and acting < len(chain) - 1
    if passes_up:
        c.approval_step = acting + 1
        next_user = db.get(User, chain[acting + 1])
        message = f"Approved -- passed to {display_name(next_user) if next_user else 'the next head'}."
    else:
        if acting is not None:
            c.approval_step = acting
        c.status = "approved"
        c.decided_by_user_id = current_user.id
        c.decided_at = datetime.utcnow()
        apply_correction(db, c, current_user)
        message = "Approved -- the attendance is updated."
    db.commit()
    return {"message": message, "id": c.id, "status": c.status}


@router.post("/time-corrections/{correction_id}/reject")
def reject_time_correction(
    correction_id: int,
    payload: DecisionIn = Body(DecisionIn()),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.get(TimeCorrectionRequest, correction_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found.")
    chain, _, skipped = _acting(db, c, current_user)
    c.approval_log = log_skipped(db, c.approval_log, chain, skipped)
    c.approval_log = append_log(
        c.approval_log, current_user, "rejected", (payload.remarks or "").strip() or None
    )
    c.status = "rejected"
    c.decided_by_user_id = current_user.id
    c.decided_at = datetime.utcnow()
    db.commit()
    return {"message": "Rejected.", "id": c.id, "status": c.status}
