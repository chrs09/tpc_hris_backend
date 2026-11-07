# app/api/schedule_changes.py
#
# Schedule changes (ticket "Work sched - Manager"): an employee with a
# fixed schedule asks for a different time in / out on ONE date, before
# that day. The Org Chart heads with "Schedule Change" ticked approve in
# turn. Once approved, that date's expected schedule is the new times --
# late, undertime, expected hours, overtime start, the missed time in
# alert and payroll all follow it. The regular schedule never changes.
# Who may file: Employee.allow_schedule_change (set per employee on the
# 201), and not drivers / helpers (attendance from trips).

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user, has_editable_grant
from app.models.employees import Employee
from app.models.schedule_change import ScheduleChangeRequest
from app.models.user import User
from app.services.approval_chain import (
    acting_index,
    append_log,
    can_view_all_payroll,
    describe_chain,
    dump_chain,
    effective_step,
    load_json_list,
    log_skipped,
    resolve_chain,
    team_scope,
)
from app.services.attendance_alerts import is_trip_based, now_ph
from app.services.payroll_lock import ensure_unlocked
from app.utils.user_display import display_name

router = APIRouter(prefix="/schedule-changes", tags=["Schedule Changes"])

KIND = "schedule_change"
# Superadmin, or an Attendance grid "Can edit" grant, can finish any one.
EDIT_GRANTS = ["hris.attendance_grid_view"]
LOOKAHEAD_DAYS = 90


def _clock(t: time | None) -> str | None:
    return t.strftime("%I:%M %p").lstrip("0") if t else None


def _hhmm(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def _parse(value: str, label: str) -> time:
    try:
        return datetime.strptime((value or "").strip(), "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label}: use a time like 08:00.")


def _name(emp: Employee | None) -> str | None:
    return " ".join(f"{emp.first_name or ''} {emp.last_name or ''}".split()) if emp else None


def _regular(employee: Employee | None, day: date) -> tuple[str | None, str | None]:
    """The regular schedule's stored times that weekday, as stored ("HH:MM:SS")."""
    schedule = employee.schedule_template if employee else None
    if not schedule:
        return None, None
    name = day.strftime("%A").lower()
    raw = lambda t: t.strftime("%H:%M:%S") if t else None  # noqa: E731
    return raw(getattr(schedule, f"{name}_in", None)), raw(getattr(schedule, f"{name}_out", None))


def _current_approver(db: Session, c: ScheduleChangeRequest) -> int | None:
    chain = [int(i) for i in load_json_list(c.approval_chain)]
    if not chain:
        return None
    index, _ = effective_step(db, chain, c.approval_step or 0)
    return chain[index] if index < len(chain) else None


def _payload(db: Session, c: ScheduleChangeRequest, user: User | None = None, sees_all=False) -> dict:
    progress = describe_chain(db, c.approval_chain, c.approval_step, c.approval_log, c.status != "pending")
    current = _current_approver(db, c) if c.status == "pending" else None
    regular_in, regular_out = _regular(c.employee, c.schedule_date)
    return {
        "id": c.id,
        "employee_id": c.employee_id,
        "employee_name": _name(c.employee),
        "position": c.employee.position if c.employee else None,
        "schedule_date": str(c.schedule_date),
        "date_label": c.schedule_date.strftime("%a, %b %d, %Y"),
        "time_in": _hhmm(c.time_in),
        "time_out": _hhmm(c.time_out),
        "time_in_label": _clock(c.time_in),
        "time_out_label": _clock(c.time_out),
        # The regular schedule that day, as stored (the web shows it the
        # same way the Work Schedules page does).
        "regular_in_raw": regular_in,
        "regular_out_raw": regular_out,
        "reason": c.reason,
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        **progress,
        "can_act": bool(user) and c.status == "pending" and (current == user.id or sees_all),
    }


def _employee_of(db: Session, user: User) -> Employee | None:
    return db.get(Employee, user.employee_id) if user.employee_id else None


def _eligibility(db: Session, user: User) -> tuple[bool, str | None, Employee | None]:
    employee = _employee_of(db, user)
    if not employee:
        return False, "Your login isn't linked to an employee.", None
    if is_trip_based(employee, user):
        return False, "Your attendance comes from your trips.", employee
    if not employee.allow_schedule_change:
        return False, "Schedule changes aren't turned on for you -- ask HR.", employee
    return True, None, employee


@router.get("/eligibility")
def schedule_change_eligibility(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Whether this person may request a schedule change (shows the
    feature on their dashboard / app)."""
    ok, reason, _ = _eligibility(db, current_user)
    return {"can_file": ok, "reason": reason}


class ChangeIn(BaseModel):
    schedule_date: date
    time_in: str  # "HH:MM", PH
    time_out: str
    reason: str


@router.post("")
def file_schedule_change(
    payload: ChangeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ok, why, employee = _eligibility(db, current_user)
    if not ok:
        raise HTTPException(status_code=403, detail=why)
    today = now_ph().date()
    day = payload.schedule_date
    # Prior approval: filed before the day.
    if day <= today:
        raise HTTPException(status_code=400, detail="File it before the day -- pick tomorrow or later.")
    if day > today + timedelta(days=LOOKAHEAD_DAYS):
        raise HTTPException(status_code=400, detail=f"Pick a day within the next {LOOKAHEAD_DAYS} days.")
    start = _parse(payload.time_in, "Time in")
    end = _parse(payload.time_out, "Time out")
    if start == end:
        raise HTTPException(status_code=400, detail="Time in and time out can't be the same.")
    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Say why you need a different time.")
    taken = (
        db.query(ScheduleChangeRequest.id)
        .filter(
            ScheduleChangeRequest.employee_id == employee.id,
            ScheduleChangeRequest.schedule_date == day,
            ScheduleChangeRequest.status.in_(("pending", "approved")),
        )
        .first()
    )
    if taken:
        raise HTTPException(
            status_code=400,
            detail="You already have a schedule change for that day -- cancel it to file again.",
        )
    chain = resolve_chain(db, employee, current_user, KIND)
    change = ScheduleChangeRequest(
        employee_id=employee.id,
        schedule_date=day,
        time_in=start,
        time_out=end,
        reason=reason[:1000],
        status="pending",
        approval_chain=dump_chain(chain),
        approval_step=0,
        approval_log=append_log(None, current_user, "filed", reason[:300]),
        filed_by_user_id=current_user.id,
    )
    db.add(change)
    db.commit()
    return {"message": "Schedule change filed.", "id": change.id}


@router.get("/mine")
def my_schedule_changes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.employee_id:
        return []
    items = (
        db.query(ScheduleChangeRequest)
        .options(joinedload(ScheduleChangeRequest.employee))
        .filter(ScheduleChangeRequest.employee_id == current_user.employee_id)
        .order_by(ScheduleChangeRequest.schedule_date.desc(), ScheduleChangeRequest.id.desc())
        .limit(60)
        .all()
    )
    return [_payload(db, c) for c in items]


@router.post("/{change_id}/cancel")
def cancel_schedule_change(
    change_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.get(ScheduleChangeRequest, change_id)
    if not c or c.employee_id != current_user.employee_id:
        raise HTTPException(status_code=404, detail="Not found.")
    if c.status == "approved" and c.schedule_date <= now_ph().date():
        raise HTTPException(status_code=400, detail="That day has started -- it can't be cancelled now.")
    if c.status not in ("pending", "approved"):
        raise HTTPException(status_code=400, detail="This can't be cancelled.")
    c.status = "cancelled"
    c.decided_at = datetime.utcnow()
    c.approval_log = append_log(c.approval_log, current_user, "cancelled")
    db.commit()
    return {"message": "Cancelled -- your regular schedule applies that day."}


# =====================================================================
# APPROVERS (Org Chart heads with "Schedule Change")
# =====================================================================
@router.get("/for-my-approval")
def schedule_changes_for_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pending ones whose turn is mine -- or, for a superadmin /
    Attendance grid "Can edit", every pending one (a head: their team)."""
    sees_all = has_editable_grant(db, current_user, EDIT_GRANTS)
    items = (
        db.query(ScheduleChangeRequest)
        .options(joinedload(ScheduleChangeRequest.employee))
        .filter(ScheduleChangeRequest.status == "pending")
        .order_by(ScheduleChangeRequest.schedule_date.asc())
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
        result.append(_payload(db, c, current_user, sees_all))
    return result


def _acting(db: Session, c: ScheduleChangeRequest, user: User):
    if c.status != "pending":
        raise HTTPException(status_code=400, detail="This request is already decided.")
    if user.employee_id and user.employee_id == c.employee_id:
        raise HTTPException(status_code=403, detail="Someone else has to approve your own request.")
    chain = [int(i) for i in load_json_list(c.approval_chain)]
    acting, skipped = acting_index(db, chain, c.approval_step, user.id) if chain else (None, [])
    if acting is None and not has_editable_grant(db, user, EDIT_GRANTS):
        raise HTTPException(status_code=403, detail="It isn't your turn to approve this.")
    return chain, acting, skipped


@router.post("/{change_id}/approve")
def approve_schedule_change(
    change_id: int,
    remarks: str | None = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.get(ScheduleChangeRequest, change_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found.")
    chain, acting, skipped = _acting(db, c, current_user)
    # Approved late (after the day) can't reach a payroll already locked.
    ensure_unlocked(db, c.employee_id, c.schedule_date, "the schedule")
    c.approval_log = log_skipped(db, c.approval_log, chain, skipped)
    c.approval_log = append_log(c.approval_log, current_user, "approved", (remarks or "").strip() or None)
    if acting is not None and acting < len(chain) - 1:
        c.approval_step = acting + 1
        next_user = db.get(User, chain[acting + 1])
        message = f"Approved -- passed to {display_name(next_user) if next_user else 'the next head'}."
    else:
        if acting is not None:
            c.approval_step = acting
        c.status = "approved"
        c.decided_by_user_id = current_user.id
        c.decided_at = datetime.utcnow()
        message = "Approved -- that day uses the new schedule."
    db.commit()
    return {"message": message, "id": c.id, "status": c.status}


@router.post("/{change_id}/reject")
def reject_schedule_change(
    change_id: int,
    remarks: str | None = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.get(ScheduleChangeRequest, change_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found.")
    chain, _, skipped = _acting(db, c, current_user)
    c.approval_log = log_skipped(db, c.approval_log, chain, skipped)
    c.approval_log = append_log(c.approval_log, current_user, "rejected", (remarks or "").strip() or None)
    c.status = "rejected"
    c.decided_by_user_id = current_user.id
    c.decided_at = datetime.utcnow()
    db.commit()
    return {"message": "Rejected -- the regular schedule applies.", "id": c.id, "status": c.status}


# =====================================================================
# APPROVED CHANGES -- for the payroll / attendance pages
# =====================================================================
@router.get("/approved")
def approved_schedule_changes(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """{"<employee id>": {"YYYY-MM-DD": {"time_in": "HH:MM", "time_out":
    "HH:MM"}}} (PH) -- everyone for payroll access, a head's team, or
    just yourself."""
    if (end - start).days > 120:
        raise HTTPException(status_code=400, detail="Pick at most 120 days.")
    query = db.query(ScheduleChangeRequest).filter(
        ScheduleChangeRequest.status == "approved",
        ScheduleChangeRequest.schedule_date >= start,
        ScheduleChangeRequest.schedule_date <= end,
    )
    if not can_view_all_payroll(db, current_user):
        team = team_scope(db, current_user)
        ids = set(team["employee_ids"]) if team else set()
        if current_user.employee_id:
            ids.add(current_user.employee_id)
        query = query.filter(ScheduleChangeRequest.employee_id.in_(ids or {0}))
    result: dict = {}
    for c in query:
        result.setdefault(str(c.employee_id), {})[str(c.schedule_date)] = {
            "time_in": _hhmm(c.time_in),
            "time_out": _hhmm(c.time_out),
        }
    return result
