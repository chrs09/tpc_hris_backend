"""Internal work history (201 -> Work History): department, position, pay
type and rates from an effective date (app/models/employee_job_change.py).

- record_change(): a change effective today or earlier updates the
  employee now; a future one is SCHEDULED and applied on its date by
  apply_due_changes() (run at startup and whenever the 201 / payroll
  loads).
- state_on(): what was true for an employee on a given day.
- segments(): an employee's spans within a cutoff, one per department /
  pay setting -- payroll pays each span in its own department.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.employee_job_change import EmployeeJobChange
from app.models.employees import Employee

FIELDS = (
    "department",
    "position",
    "employment_type",
    "payroll_type",
    "daily_rate",
    "monthly_basic",
    "monthly_allow",
    "schedule_template_id",
)
ACTIVE = ("APPLIED", "SCHEDULED")


def today_ph() -> date:
    return datetime.now(ZoneInfo("Asia/Manila")).date()


def _value(v):
    if v is None:
        return None
    try:
        return float(v) if not isinstance(v, (str, int)) else v
    except (TypeError, ValueError):
        return v


def snapshot(source) -> dict:
    return {field: _value(getattr(source, field, None)) for field in FIELDS}


def ensure_starting_row(db: Session, employee: Employee) -> None:
    """Employees added after the migration (new hire, applicant) get their
    HIRED row the first time their history is touched."""
    exists = (
        db.query(EmployeeJobChange.id)
        .filter(EmployeeJobChange.employee_id == employee.id)
        .first()
    )
    if exists:
        return
    now = datetime.utcnow()
    db.add(
        EmployeeJobChange(
            employee_id=employee.id,
            effective_date=employee.date_hired or today_ph(),
            kind="HIRED",
            status="APPLIED",
            reason="Starting record",
            created_at=now,
            applied_at=now,
            **{field: getattr(employee, field) for field in FIELDS},
        )
    )
    db.flush()


def _rows(db: Session, employee_ids=None):
    query = db.query(EmployeeJobChange).filter(EmployeeJobChange.status.in_(ACTIVE))
    if employee_ids is not None:
        query = query.filter(EmployeeJobChange.employee_id.in_(list(employee_ids) or [0]))
    return query.order_by(
        EmployeeJobChange.employee_id,
        EmployeeJobChange.effective_date,
        EmployeeJobChange.id,
    ).all()


def state_on(db: Session, employee: Employee, day: date) -> dict:
    """The employee's department / position / pay on `day`; falls back to
    the employee record when there's no history yet."""
    row = (
        db.query(EmployeeJobChange)
        .filter(
            EmployeeJobChange.employee_id == employee.id,
            EmployeeJobChange.status.in_(ACTIVE),
            EmployeeJobChange.effective_date <= day,
        )
        .order_by(EmployeeJobChange.effective_date.desc(), EmployeeJobChange.id.desc())
        .first()
    )
    return snapshot(row or employee)


def department_on(db: Session, employee: Employee | None, day) -> str | None:
    if employee is None:
        return None
    if isinstance(day, datetime):
        day = day.date()
    if not isinstance(day, date):
        return employee.department
    return state_on(db, employee, day)["department"]


def _apply(employee: Employee, row: EmployeeJobChange) -> None:
    for field in FIELDS:
        setattr(employee, field, getattr(row, field))


def apply_due_changes(db: Session) -> int:
    """Scheduled changes whose date has come: copy them onto the employee."""
    due = (
        db.query(EmployeeJobChange)
        .filter(
            EmployeeJobChange.status == "SCHEDULED",
            EmployeeJobChange.effective_date <= today_ph(),
        )
        .order_by(EmployeeJobChange.effective_date, EmployeeJobChange.id)
        .all()
    )
    for row in due:
        employee = db.get(Employee, row.employee_id)
        if employee:
            _apply(employee, row)
        row.status = "APPLIED"
        row.applied_at = datetime.utcnow()
    if due:
        db.commit()
    return len(due)


def record_change(db: Session, employee: Employee, values: dict, effective: date, reason: str, user) -> EmployeeJobChange:
    from app.services.payroll_lock import locked_run

    ensure_starting_row(db, employee)
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Give the reason for the change.")
    if employee.date_hired and effective < employee.date_hired:
        raise HTTPException(status_code=400, detail="The effective date can't be before the date hired.")

    before = state_on(db, employee, effective)
    after = {**before, **{k: v for k, v in values.items() if k in FIELDS}}
    if snapshot_equal(before, after):
        raise HTTPException(status_code=400, detail="Nothing changed -- edit at least one field.")

    # Paid periods stay as paid: not into a locked cutoff of either side.
    for dept in {before["department"], after["department"]}:
        run = locked_run(db, dept, effective)
        if run:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Payroll for {run.department} {run.period_start:%b %d}–"
                    f"{run.period_end:%b %d, %Y} is {run.status.lower()}; pick an "
                    "effective date after it."
                ),
            )

    same_day = (
        db.query(EmployeeJobChange)
        .filter(
            EmployeeJobChange.employee_id == employee.id,
            EmployeeJobChange.status.in_(ACTIVE),
            EmployeeJobChange.effective_date == effective,
        )
        .first()
    )
    if same_day and same_day.kind == "HIRED":
        raise HTTPException(status_code=400, detail="Pick a date after the date hired.")
    if same_day:
        raise HTTPException(
            status_code=400,
            detail="There's already a change on that date -- cancel it first or pick another date.",
        )

    is_future = effective > today_ph()
    now = datetime.utcnow()
    row = EmployeeJobChange(
        employee_id=employee.id,
        effective_date=effective,
        kind="CHANGE",
        status="SCHEDULED" if is_future else "APPLIED",
        reason=reason,
        created_by_user_id=user.id if user else None,
        created_at=now,
        applied_at=None if is_future else now,
        **after,
    )
    db.add(row)
    db.flush()
    if not is_future:
        # The employee record shows what's in effect today.
        _apply_current(db, employee)
    return row


def _apply_current(db: Session, employee: Employee) -> None:
    current = state_on(db, employee, today_ph())
    for field, value in current.items():
        setattr(employee, field, value)


def cancel_change(db: Session, employee: Employee, row: EmployeeJobChange) -> None:
    from app.services.payroll_lock import locked_run

    if row.kind == "HIRED":
        raise HTTPException(status_code=400, detail="The starting record can't be removed.")
    if row.status == "CANCELLED":
        return
    for dept in {row.department, state_on(db, employee, row.effective_date - timedelta(days=1))["department"]}:
        run = locked_run(db, dept, row.effective_date)
        if run:
            raise HTTPException(
                status_code=409,
                detail=f"Payroll for {run.department} covering that date is {run.status.lower()}.",
            )
    row.status = "CANCELLED"
    row.cancelled_at = datetime.utcnow()
    db.flush()
    _apply_current(db, employee)


def snapshot_equal(a: dict, b: dict) -> bool:
    def norm(v):
        if v in ("", None):
            return None
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return str(v).strip()

    return all(norm(a.get(f)) == norm(b.get(f)) for f in FIELDS)


def segments(db: Session, start: date, end: date, employee_ids=None) -> dict:
    """{employee_id: [{"from", "to", "is_last", **fields}]} -- the employee's
    spans within start..end, split wherever a change takes effect. Only
    employees that have history; others are one span of their record."""
    by_employee: dict[int, list] = {}
    for row in _rows(db, employee_ids):
        by_employee.setdefault(row.employee_id, []).append(row)

    result = {}
    for employee_id, rows in by_employee.items():
        spans = []
        for i, row in enumerate(rows):
            span_start = row.effective_date
            span_end = rows[i + 1].effective_date - timedelta(days=1) if i + 1 < len(rows) else end
            lo, hi = max(span_start, start), min(span_end, end)
            if lo > hi:
                continue
            spans.append({"from": lo.isoformat(), "to": hi.isoformat(), **snapshot(row)})
        # Merge back-to-back spans in the same department and pay.
        merged = []
        for span in spans:
            if merged and snapshot_equal(merged[-1], span):
                merged[-1]["to"] = span["to"]
            else:
                merged.append(span)
        for i, span in enumerate(merged):
            span["is_last"] = i == len(merged) - 1
        if merged:
            result[employee_id] = merged
    return result
