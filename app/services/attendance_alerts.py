"""Missed time in -- a scheduled employee who hasn't timed in.

Every few minutes (start_background_checks, from app/main.py) this looks
at each active, scheduled employee (not drivers / helpers: their
attendance comes from trips):

* Today: once their scheduled time in + the wait time (company setting,
  default 2 hours) has passed with no time in, an AttendanceAlert goes to
  their immediate head (Approvals -> Attendance) and the head gets an
  email. Late -> the day becomes Delay when they time in; 2nd half ->
  Halfday; Absent -> Absent now, with a reason.
* Earlier days of the current cutoff with no attendance: the head is asked
  "Does this employee work on this day?" -- No = Absent (reason), Yes =
  the employee is emailed to file a time correction.

Skipped: approved leave, a national non-working holiday, a day with
attendance (time in, On Leave, Absent, Rest Day), days before they were
hired, and days inside locked payroll. Each employee + day is asked once
(unique per day, so several server workers can't double it). Timing in
closes it (on_time_in). Nobody is ever marked Absent automatically.
"""

import logging
import threading
import time as time_module
from datetime import date, datetime, time, timedelta
from html import escape
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.app_setting import AppSetting
from app.models.attendance import AttendanceRecord
from app.models.attendance_adjustment import AttendanceAdjustment
from app.models.attendance_alert import AttendanceAlert
from app.models.employees import Employee
from app.models.holiday import Holiday
from app.models.leave_request import LeaveRequest
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

PH = ZoneInfo("Asia/Manila")

WAIT_SETTING = "missed_time_in_alert_minutes"
DEFAULT_WAIT_MINUTES = 120
CHECK_EVERY_SECONDS = 5 * 60

# A day with one of these needs no time in.
NO_TIME_IN_STATUSES = ("On Leave", "Absent", "Rest Day")
# Holidays nobody is expected to work (national only).
NON_WORKING_HOLIDAYS = ("regular", "special_non_working")
# Still needs the head's answer / waiting for something.
ACTIVE_STATUSES = ("open", "waiting_time_in", "waiting_employee")

# Head's choice -> the day's status once they time in.
STATUS_ON_TIME_IN = {"late": "Delay", "second_half": "Halfday"}


def now_ph() -> datetime:
    return datetime.now(PH)


def wait_minutes(db: Session) -> int:
    setting = db.query(AppSetting).filter(AppSetting.key == WAIT_SETTING).first()
    try:
        return max(0, int(setting.value)) if setting else DEFAULT_WAIT_MINUTES
    except ValueError:
        return DEFAULT_WAIT_MINUTES


def scheduled_in(employee: Employee, day: date) -> time | None:
    """Their time in that day per their schedule (None = not scheduled)."""
    schedule = employee.schedule_template
    if not schedule:
        return None
    day_name = day.strftime("%A").lower()
    if not getattr(schedule, f"{day_name}_out", None):
        return None
    return getattr(schedule, f"{day_name}_in", None)


def _role(user: User | None) -> str:
    if not user:
        return ""
    return (getattr(user.role, "value", user.role) or "").lower()


def is_trip_based(employee: Employee, user: User | None) -> bool:
    """Drivers and helpers: attendance comes from their trips."""
    department = (employee.department or "").lower()
    return _role(user) in ("driver", "helper") or "driver" in department or "helper" in department


def pick_head(db: Session, employee: Employee, user: User | None, day: date) -> int | None:
    """The immediate head, else the next head up when they're out that
    day. None = nobody on the Org Chart (superadmins answer it)."""
    from app.services.approval_chain import approver_away, immediate_head, resolve_chain

    candidates = []
    for uid in [immediate_head(db, employee, user), *resolve_chain(db, employee, user, "attendance")]:
        if uid and uid not in candidates and (not user or uid != user.id):
            candidates.append(uid)
    for uid in candidates:
        head = db.get(User, uid)
        if head and head.is_active and not approver_away(db, uid, day):
            return uid
    return None


def _is_locked(db: Session, employee_id: int, day: date) -> bool:
    from fastapi import HTTPException

    from app.services.payroll_lock import ensure_unlocked

    try:
        ensure_unlocked(db, employee_id, day, "attendance")
        return False
    except HTTPException:
        return True


def _employee_name(employee: Employee | None) -> str:
    if not employee:
        return "Employee"
    return f"{employee.first_name} {employee.last_name}".strip()


def _clock(value: time | None) -> str:
    return value.strftime("%I:%M %p").lstrip("0") if value else "-"


# ---------------------------------------------------------------- scan
def scan(db: Session, now: datetime | None = None) -> list[AttendanceAlert]:
    """Creates the alerts that are due; returns the new ones."""
    from app.services.payroll_cutoffs import employee_cutoff

    now = (now or now_ph()).astimezone(PH)
    today = now.date()
    wait = timedelta(minutes=wait_minutes(db))

    employees = (
        db.query(Employee)
        .options(joinedload(Employee.schedule_template))
        .filter(Employee.is_active == 1, Employee.schedule_template_id.isnot(None))
        .all()
    )
    if not employees:
        return []
    users = {
        u.employee_id: u
        for u in db.query(User).filter(User.employee_id.isnot(None)).all()
    }
    employees = [e for e in employees if not is_trip_based(e, users.get(e.id))]

    # The days to look at: each employee's current cutoff up to today.
    ranges = {}
    for employee in employees:
        try:
            start, _ = employee_cutoff(db, employee, today)
        except Exception:
            start = today
        if employee.date_hired and employee.date_hired > start:
            start = employee.date_hired
        if start <= today:
            ranges[employee.id] = start
    if not ranges:
        return []
    first = min(ranges.values())
    ids = list(ranges)

    records = {
        (r.employee_id, r.attendance_date): r
        for r in db.query(AttendanceRecord).filter(
            AttendanceRecord.employee_id.in_(ids),
            AttendanceRecord.attendance_date >= first,
            AttendanceRecord.attendance_date <= today,
        )
    }
    leaves = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id.in_(ids),
            LeaveRequest.status == "approved",
            LeaveRequest.end_date >= first,
            LeaveRequest.start_date <= today,
        )
        .all()
    )
    on_leave = {}
    for leave in leaves:
        on_leave.setdefault(leave.employee_id, []).append((leave.start_date, leave.end_date))
    holidays = {
        h.holiday_date
        for h in db.query(Holiday).filter(
            Holiday.is_active.is_(True),
            Holiday.scope == "national",
            Holiday.holiday_type.in_(NON_WORKING_HOLIDAYS),
            Holiday.holiday_date >= first,
            Holiday.holiday_date <= today,
        )
    }
    asked = {
        (a.employee_id, a.attendance_date)
        for a in db.query(AttendanceAlert.employee_id, AttendanceAlert.attendance_date).filter(
            AttendanceAlert.employee_id.in_(ids),
            AttendanceAlert.attendance_date >= first,
        )
    }

    created = []
    for employee in employees:
        if employee.id not in ranges:
            continue
        day = ranges[employee.id]
        while day <= today:
            this_day, day = day, day + timedelta(days=1)
            sched = scheduled_in(employee, this_day)
            if not sched or (employee.id, this_day) in asked or this_day in holidays:
                continue
            if this_day == today and now < datetime.combine(today, sched, PH) + wait:
                continue
            if any(start <= this_day <= end for start, end in on_leave.get(employee.id, [])):
                continue
            record = records.get((employee.id, this_day))
            if record and (record.check_in_time or record.status in NO_TIME_IN_STATUSES):
                continue
            if _is_locked(db, employee.id, this_day):
                continue
            alert = AttendanceAlert(
                employee_id=employee.id,
                attendance_date=this_day,
                scheduled_in=sched,
                head_user_id=pick_head(db, employee, users.get(employee.id), this_day),
                status="open",
            )
            db.add(alert)
            try:
                db.commit()
            except IntegrityError:
                # Another server worker made it first.
                db.rollback()
                continue
            created.append(alert)
    return created


# ---------------------------------------------------------------- time in
def on_time_in(db: Session, record: AttendanceRecord) -> None:
    """They timed in: close that day's alert. If the head said Late / 2nd
    half, the day becomes Delay / Halfday. Call after the record has an
    id; the caller commits."""
    alert = (
        db.query(AttendanceAlert)
        .filter(
            AttendanceAlert.employee_id == record.employee_id,
            AttendanceAlert.attendance_date == record.attendance_date,
            AttendanceAlert.status.in_(("open", "waiting_time_in")),
        )
        .first()
    )
    if not alert:
        return
    new_status = STATUS_ON_TIME_IN.get(alert.decision)
    if new_status and record.status != new_status:
        db.add(
            AttendanceAdjustment(
                attendance_id=record.id,
                field="status",
                old_value=record.status,
                new_value=new_status,
                reason=(
                    "Missed time in -- head marked it "
                    f"{'Late' if alert.decision == 'late' else '2nd half'}"
                ),
                changed_by_user_id=alert.decided_by_user_id,
            )
        )
        record.status = new_status
    alert.decision = alert.decision or "timed_in"
    alert.status = "closed"
    alert.closed_at = datetime.utcnow()


def sweep(db: Session) -> None:
    """Closes alerts whose employee has since timed in (e.g. an entry not
    made through the phone / kiosk)."""
    alerts = (
        db.query(AttendanceAlert)
        .filter(AttendanceAlert.status.in_(("open", "waiting_time_in")))
        .all()
    )
    changed = False
    for alert in alerts:
        record = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.employee_id == alert.employee_id,
                AttendanceRecord.attendance_date == alert.attendance_date,
            )
            .first()
        )
        if record and record.check_in_time:
            on_time_in(db, record)
            changed = True
        elif record and record.status in NO_TIME_IN_STATUSES:
            alert.status = "closed"
            alert.decision = alert.decision or record.status.lower().replace(" ", "_")
            alert.closed_at = datetime.utcnow()
            changed = True
    if changed:
        db.commit()


# ---------------------------------------------------------------- emails
def _user_email(db: Session, user: User | None) -> str | None:
    if not user:
        return None
    if user.email:
        return user.email
    if user.employee_id:
        employee = db.get(Employee, user.employee_id)
        return employee.email if employee else None
    return None


def _approvals_url() -> str:
    from app.core.config import Settings

    return f"{Settings.FRONTEND_URL.rstrip('/')}/approvals?tab=attendance"


def email_heads(db: Session, alerts: list[AttendanceAlert]) -> None:
    """One email per head listing their new alerts (no head: every active
    superadmin with an email)."""
    from app.services.email_service import _email_button, send_email

    if not alerts:
        return
    today = now_ph().date()
    by_head: dict[int | None, list] = {}
    for alert in alerts:
        by_head.setdefault(alert.head_user_id, []).append(alert)

    for head_id, items in by_head.items():
        if head_id:
            recipients = [db.get(User, head_id)]
        else:
            recipients = (
                db.query(User)
                .filter(User.is_active.is_(True), User.role == UserRole.SUPERADMIN)
                .all()
            )
        today_items = [a for a in items if a.attendance_date == today]
        past_items = [a for a in items if a.attendance_date != today]
        rows = []
        if today_items:
            rows.append(
                "<p style='color:#334155;font-size:14px;'>Not timed in yet today "
                "-- is this late, absent, or working the 2nd half?</p><ul>"
                + "".join(
                    f"<li>{escape(_employee_name(a.employee))} "
                    f"(scheduled {_clock(a.scheduled_in)})</li>"
                    for a in today_items
                )
                + "</ul>"
            )
        if past_items:
            rows.append(
                "<p style='color:#334155;font-size:14px;'>Missing attendance this "
                "cutoff -- does this employee work on this day?</p><ul>"
                + "".join(
                    f"<li>{escape(_employee_name(a.employee))} -- "
                    f"{a.attendance_date:%a, %b %d}</li>"
                    for a in past_items
                )
                + "</ul>"
            )
        subject = (
            f"Not timed in yet: {_employee_name(today_items[0].employee)}"
            if len(items) == 1 and today_items
            else f"Attendance to check: {len(items)} employee day(s)"
        )
        for head in recipients:
            to = _user_email(db, head)
            if not to:
                logger.info("Missed time in: no email for user %s", getattr(head, "id", None))
                continue
            html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto;">
                <h2 style="color: #0F172A;">Attendance needs your answer</h2>
                {''.join(rows)}
                {_email_button(_approvals_url(), "Open Approvals")}
                <p style="color:#64748B;font-size:12px;">If they time in first, this
                closes by itself.</p>
            </div>
            """
            try:
                send_email(to, subject, html)
            except Exception as exc:  # an email problem never stops the check
                logger.warning("Missed time in email to %s failed: %s", to, exc)
    sent = datetime.utcnow()
    for alert in alerts:
        alert.head_emailed_at = sent
    db.commit()


def email_employee_to_correct(db: Session, alert: AttendanceAlert) -> bool:
    """The head said they worked that day: ask them to file their time."""
    from app.core.config import Settings
    from app.services.email_service import _email_button, send_email

    employee = alert.employee or db.get(Employee, alert.employee_id)
    user = db.query(User).filter(User.employee_id == alert.employee_id).first()
    to = (employee.email if employee else None) or _user_email(db, user)
    if not to:
        return False
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto;">
        <h2 style="color: #0F172A;">Hello {escape(_employee_name(employee))},</h2>
        <p style="color:#334155;font-size:14px;line-height:1.6;">
            You have no time in on <strong>{alert.attendance_date:%A, %B %d}</strong>,
            and your head confirmed you worked that day. Please file a time
            correction with your actual time in / out and the reason, so it can be
            approved and counted.
        </p>
        {_email_button(f"{Settings.FRONTEND_URL.rstrip('/')}/dashboard", "File Time Correction")}
    </div>
    """
    try:
        return send_email(to, f"Time in needed for {alert.attendance_date:%b %d}", html)
    except Exception as exc:
        logger.warning("Time correction email to %s failed: %s", to, exc)
        return False


# ---------------------------------------------------------------- timer
def run_once() -> int:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        sweep(db)
        created = scan(db)
        email_heads(db, created)
        return len(created)
    finally:
        db.close()


_started = False


def start_background_checks() -> None:
    """A daemon thread: a check every CHECK_EVERY_SECONDS. Errors are
    logged and the next round tries again."""
    global _started
    if _started:
        return
    _started = True

    def loop():
        time_module.sleep(60)
        while True:
            try:
                count = run_once()
                if count:
                    logger.info("Missed time in: %s new alert(s)", count)
            except Exception as exc:
                logger.warning("Missed time in check failed: %s", exc)
            time_module.sleep(CHECK_EVERY_SECONDS)

    threading.Thread(target=loop, name="missed-time-in", daemon=True).start()
