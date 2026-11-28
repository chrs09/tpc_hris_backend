"""Change a trip's date (and start time) after the fact -- superadmin only.

Trips sometimes get encoded on the wrong day (e.g. done Nov 7, started in
the app Nov 9), or in the wrong order (a 2nd trip that was really the
1st). Pay, incentives and "Nth trip of the day" all go by the trip's start
time, so this moves it.

Rules:
- superadmin only;
- not a cancelled or archived trip, and not to a day in the future;
- never when the payroll of the old OR the new day is locked (driver and
  helpers);
- start, end and dispatch times all move by the same amount, so the trip
  keeps its length and its place among the driver's trips;
- every change is logged on the trip (Remarks) with who, when, the old
  and new date / time and the reason;
- a pay run already generated keeps its saved figures until regenerated.
"""

from datetime import date, datetime, time

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.attendance import AttendanceRecord
from app.models.trip_bypass_log import TripBypassLog
from app.models.trip_helper import TripHelper
from app.models.trips import Trip, TripStatus
from app.models.user import User
from app.utils.timezone import ph_to_utc, utc_to_ph

ACTION = "change-date"


def _when(trip):
    return trip.start_time or trip.created_at


def ph_start(trip) -> datetime | None:
    when = _when(trip)
    return utc_to_ph(when).replace(tzinfo=None) if when else None


def fmt(dt: datetime | None) -> str:
    if not dt:
        return "none"
    return dt.strftime("%b %d, %Y %I:%M %p").replace(" 0", " ")


def _parse_time(value: str | None, fallback: time) -> time:
    if not value:
        return fallback
    try:
        hh, mm = value.strip().split(":")[:2]
        return time(int(hh), int(mm))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Use a time like 08:30.")


def new_ph_start(trip, new_day: date, new_time: str | None) -> datetime:
    old = ph_start(trip) or datetime.combine(new_day, time(8, 0))
    return datetime.combine(new_day, _parse_time(new_time, old.time().replace(second=0, microsecond=0)))


def _people(db: Session, trip) -> list[tuple[int, str, str]]:
    """(employee_id, name, role) for the driver and helpers."""
    from app.utils.user_display import display_name

    out = []
    driver = db.query(User).filter(User.id == trip.driver_id).first() if trip.driver_id else None
    if driver and driver.employee_id:
        out.append((driver.employee_id, display_name(driver), "Driver"))
    from app.models.employees import Employee

    for (helper_id,) in db.query(TripHelper.helper_id).filter(TripHelper.trip_id == trip.id):
        emp = db.query(Employee).filter(Employee.id == helper_id).first()
        name = " ".join(p for p in [getattr(emp, "first_name", None), getattr(emp, "last_name", None)] if p) if emp else None
        out.append((helper_id, name or f"Employee #{helper_id}", "Helper"))
    return out


def _lock_problem(db: Session, people, day: date) -> str | None:
    from app.services.payroll_lock import ensure_unlocked

    for employee_id, _name, _role in people:
        try:
            ensure_unlocked(db, employee_id, day, "this trip")
        except HTTPException as error:
            return str(error.detail)
    return None


def day_trips(db: Session, trip, day: date, moved_start: datetime) -> list[dict]:
    """The driver's trips on `day` (PH) in order, with this trip at its new
    time -- shows what it'll be (1st, 2nd ...)."""
    lo = ph_to_utc(datetime.combine(day, time.min))
    hi = ph_to_utc(datetime.combine(day, time.max))
    others = (
        db.query(Trip)
        .filter(
            Trip.driver_id == trip.driver_id,
            Trip.id != trip.id,
            Trip.start_time >= lo,
            Trip.start_time <= hi,
            Trip.status != TripStatus.CANCELLED,
            Trip.is_archived.is_(False),
        )
        .all()
    ) if trip.driver_id else []
    rows = [
        {
            "id": t.id,
            "trip_code": t.trip_code,
            "shipment": t.ticket_no,
            "start": utc_to_ph(t.start_time).replace(tzinfo=None),
            "this": False,
        }
        for t in others
    ]
    rows.append({"id": trip.id, "trip_code": trip.trip_code, "shipment": trip.ticket_no, "start": moved_start, "this": True})
    rows.sort(key=lambda r: (r["start"], r["id"]))
    return [
        {**r, "nth": i + 1, "start": r["start"].strftime("%I:%M %p").lstrip("0")}
        for i, r in enumerate(rows)
    ]


def check(db: Session, trip, new_day: date, new_time: str | None) -> dict:
    """{ok, problem, warnings, old, new, order} -- before saving."""
    status = getattr(trip.status, "value", trip.status)
    old = ph_start(trip)
    moved = new_ph_start(trip, new_day, new_time)
    people = _people(db, trip)
    today = utc_to_ph(datetime.utcnow()).date()

    problem = None
    if status == "CANCELLED" or trip.is_archived:
        problem = "This trip is cancelled or archived."
    elif new_day > today:
        problem = "The new date can't be in the future."
    elif old and moved == old.replace(second=0, microsecond=0):
        problem = "That's already the trip's date and time."
    else:
        problem = (old and _lock_problem(db, people, old.date())) or _lock_problem(db, people, new_day)

    # Pay needs attendance on the trip's day.
    attended = {
        e
        for (e,) in db.query(AttendanceRecord.employee_id).filter(
            AttendanceRecord.employee_id.in_([p[0] for p in people] or [-1]),
            AttendanceRecord.attendance_date == new_day,
        )
    }
    warnings = [
        f"{name} ({role}) has no attendance on {new_day.strftime('%b %d')}. The trip won't be paid "
        "until that day has attendance (Time Correction)."
        for employee_id, name, role in people
        if employee_id not in attended
    ]
    order = day_trips(db, trip, new_day, moved)
    return {
        "ok": problem is None,
        "problem": problem,
        "warnings": warnings,
        "old_date": old.date().isoformat() if old else None,
        "old_time": old.strftime("%H:%M") if old else None,
        "old_label": fmt(old),
        "new_date": new_day.isoformat(),
        "new_time": moved.strftime("%H:%M"),
        "new_label": fmt(moved),
        "nth": next((r["nth"] for r in order if r["this"]), None),
        "order": order,
    }


def change(db: Session, trip, new_day: date, new_time: str | None, user, reason: str) -> dict:
    """Moves the trip (after the checks); logs it. No commit."""
    result = check(db, trip, new_day, new_time)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["problem"])
    old = ph_start(trip)
    moved = new_ph_start(trip, new_day, new_time)
    delta = ph_to_utc(moved) - (_when(trip) or ph_to_utc(moved))
    if trip.start_time:
        trip.start_time = trip.start_time + delta
    else:
        trip.start_time = ph_to_utc(moved)
    if trip.end_time:
        trip.end_time = trip.end_time + delta
    if trip.created_at:
        trip.created_at = trip.created_at + delta
    db.add(
        TripBypassLog(
            trip_id=trip.id,
            action=ACTION,
            performed_by_user_id=user.id,
            reason=f"Trip date {fmt(old)} → {fmt(moved)}. {reason.strip()[:500]}",
        )
    )
    return {"id": trip.id, "old": fmt(old), "new": fmt(moved), "nth": result["nth"]}


def load_trip(db: Session, trip_id: int) -> Trip:
    trip = (
        db.query(Trip)
        .options(joinedload(Trip.trip_helpers))
        .filter(Trip.id == trip_id)
        .first()
    )
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return trip
