"""Once a department's payroll for a cutoff is LOCKED (or PAID), the
inputs for that period -- attendance, overtime, adjustments, trips --
can no longer change, so the paid numbers can't drift.

Call ensure_unlocked() before changing anything dated in a cutoff."""

from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.employees import Employee
from app.models.payroll_run import PayrollRun

LOCKED_STATUSES = ("LOCKED", "PAID")


def _as_date(day) -> date | None:
    if day is None:
        return None
    if isinstance(day, datetime):
        return day.date()
    if isinstance(day, date):
        return day
    try:
        return date.fromisoformat(str(day)[:10])
    except ValueError:
        return None


def locked_run(db: Session, department, day, end=None) -> PayrollRun | None:
    """The locked run covering `day` (or any day of `day`..`end`).
    `department` is a payroll name or a list of them (group + department)."""
    day = _as_date(day)
    end = _as_date(end) or day
    names = [d for d in (department if isinstance(department, (list, tuple)) else [department]) if d]
    if not names or day is None:
        return None
    return (
        db.query(PayrollRun)
        .filter(
            PayrollRun.department.in_(names),
            PayrollRun.status.in_(LOCKED_STATUSES),
            PayrollRun.period_start <= end,
            PayrollRun.period_end >= day,
        )
        .first()
    )


def ensure_unlocked(
    db: Session, employee_id: int | None, day, what: str = "this record", end=None
):
    """Raises 409 when the employee's payroll covering `day` (or any day
    up to `end`) is locked."""
    if not employee_id:
        return
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    # The department / pay they had that day (Work History), not today's --
    # paid in its payroll group (or the department, before groups).
    from app.services.job_history import state_on
    from app.services.payroll_groups import payroll_key

    if employee is None:
        return
    state = state_on(db, employee, _as_date(day)) if _as_date(day) else {
        "department": employee.department,
        "payroll_type": employee.payroll_type,
    }
    department = state.get("department")
    run = locked_run(
        db, [department, payroll_key(db, department, state.get("payroll_type"))], day, end
    )
    if run:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Payroll for {run.department} {run.period_start:%b %d}–"
                f"{run.period_end:%b %d, %Y} is {run.status.lower()}, so {what} "
                "can no longer be changed."
            ),
        )


def latest_locked_end(db: Session) -> date | None:
    """End of the latest locked/paid cutoff of a trip-paid department
    (drivers / helpers -- same rule as PayrollList's isTripBasedEmployee).
    Trip rates in effect up to here are part of a locked payroll; other
    departments (e.g. Motorpool) don't use trip rates, so their locks
    don't count."""
    from app.models.payroll_group import PayrollGroup
    from app.services.payroll_groups import TRIP_BASES

    trip_groups = [
        name
        for (name,) in db.query(PayrollGroup.name)
        .filter(PayrollGroup.pay_basis.in_(TRIP_BASES))
        .all()
    ]
    run = (
        db.query(PayrollRun)
        .filter(
            PayrollRun.status.in_(LOCKED_STATUSES),
            or_(
                PayrollRun.department.ilike("%driver%"),
                PayrollRun.department.ilike("%helper%"),
                PayrollRun.department.in_(trip_groups),
            ),
        )
        .order_by(PayrollRun.period_end.desc())
        .first()
    )
    return run.period_end if run else None


def ensure_payroll_editable(db: Session, department, cutoff_period: str | None):
    """Payroll figures (deductions, HR's OT approval) can change only
    until the run is approved -- after that, Return it for correction.
    `department` is a payroll name or a list of them (group + department)."""
    names = [d for d in (department if isinstance(department, (list, tuple)) else [department]) if d]
    if not names or not cutoff_period:
        return
    runs = (
        db.query(PayrollRun)
        .filter(
            PayrollRun.department.in_(names),
            PayrollRun.cutoff_period == cutoff_period,
        )
        .all()
    )
    run = next((r for r in runs if r.status not in ("DRAFT", "GENERATED", "FOR_REVIEW")), None)
    if run:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{run.department} payroll for this cutoff is {run.status.lower()} and can't "
                "be changed. Ask Finance to return it for correction first."
            ),
        )


def ensure_trip_unlocked(db: Session, trip, what: str = "this trip"):
    """Trips pay the driver and helpers on the trip's PH date."""
    from app.models.trip_helper import TripHelper
    from app.models.user import User
    from app.services.trip_payroll_service import to_ph

    when = trip.start_time or trip.created_at
    if when is None:
        return
    day = to_ph(when).date()
    driver = db.query(User).filter(User.id == trip.driver_id).first() if trip.driver_id else None
    employee_ids = [driver.employee_id] if driver and driver.employee_id else []
    employee_ids += [
        hid for (hid,) in db.query(TripHelper.helper_id).filter(TripHelper.trip_id == trip.id)
    ]
    for employee_id in employee_ids:
        ensure_unlocked(db, employee_id, day, what)


# Payroll steps, ticked per person on the Org Chart (Payroll -> Prepare &
# Submit / Approve & Return / Lock & Mark Paid). Role never grants these;
# superadmin always can (has_editable_grant).
PAYROLL_PREPARE = "payroll.payroll_prepare"
PAYROLL_APPROVE = "payroll.payroll_approve"
PAYROLL_RELEASE = "payroll.payroll_release"

PAYROLL_STEP_LABELS = {
    PAYROLL_PREPARE: "Prepare & Submit",
    PAYROLL_APPROVE: "Approve & Return",
    PAYROLL_RELEASE: "Lock & Mark Paid",
}


def can_payroll(db: Session, user, step: str) -> bool:
    from app.core.dependencies import has_editable_grant

    return has_editable_grant(db, user, [step])


def ensure_can_payroll(db: Session, user, step: str):
    if not can_payroll(db, user, step):
        raise HTTPException(
            status_code=403,
            detail=(
                f"You need Payroll → {PAYROLL_STEP_LABELS[step]} on the Org Chart "
                "to do this."
            ),
        )
