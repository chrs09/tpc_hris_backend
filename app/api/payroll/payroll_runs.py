"""Payroll status per department + cutoff:

    DRAFT -> GENERATED -> FOR_REVIEW -> APPROVED -> LOCKED -> PAID

Who does each step is set per person on the Org Chart (Payroll ->
Prepare & Submit / Approve & Return / Lock & Mark Paid) -- the user's
role never grants these. Superadmin can always.

- Prepare & Submit: generate (repeatable until approved; re-generating
  recalculates the same payroll_deductions rows and sends a run under
  review back to GENERATED), edit figures, submit for review.
- Approve & Return: approve, or return for correction (with a reason).
- Lock & Mark Paid: lock the period, mark it paid.
- Unlock (back to APPROVED): superadmin only, with a reason. Takes
  back the payroll's released payslips (they're released again after
  it's locked).
- Release Payslip (Lock & Mark Paid, once Locked / Paid): one employee's
  payslip, saved as Payroll had it, shows in their My Payslips.
"""

import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role_or_module
from app.models.employees import Employee
from app.models.payroll_run import PayrollRun
from app.models.payslip_release import PayslipRelease
from app.services.payroll_lock import (
    PAYROLL_APPROVE,
    PAYROLL_CONTRIBUTIONS,
    PAYROLL_PREPARE,
    PAYROLL_RELEASE,
    can_payroll,
    ensure_can_payroll,
)
from app.models.user import User
from app.services.payroll_scope import (
    allowed_employee_ids,
    allowed_payroll_groups,
    ensure_payroll_allowed,
)
from app.utils.user_display import display_name

router = APIRouter(prefix="/payroll-runs", tags=["Payroll Runs"])

_require_payroll = require_role_or_module(roles=["admin"], module_key="payroll.payroll")

# Generate (and editing figures) only before it's submitted: once it's
# For Review the snapshot is what gets approved -- anything later (e.g. a
# document after cutoff) goes in the next pay run. Return sends it back.
EDITABLE_STATUSES = ("DRAFT", "GENERATED")
STATUS_FLOW = (
    "DRAFT",
    "GENERATED",
    "FOR_REVIEW",
    # Payroll -> Government Contributions edits SSS / PhilHealth /
    # Pag-IBIG / tax only, then sends it to the head.
    "CONTRIBUTIONS",
    "HEAD_REVIEW",
    "APPROVED",
    "LOCKED",
    "PAID",
)
# Contributions edits (SSS, PhilHealth, Pag-IBIG, tax): snapshot row key
# -> payroll_deductions column.
GOV_FIELDS = {
    "sssDeduction": "sss_deduction",
    "philhealthDeduction": "philhealth_deduction",
    "pagibigDeduction": "pagibig_deduction",
    "withholdingTax": "withholding_tax",
}


def _role(user: User) -> str:
    return user.role.value if hasattr(user.role, "value") else user.role


def _period_dates(cutoff_period: str) -> tuple[date, date]:
    try:
        start, end = cutoff_period.split("_")
        return date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Cutoff period must look like 2026-10-01_2026-10-15."
        )


def _get_or_new(db: Session, department: str, cutoff_period: str) -> PayrollRun:
    run = (
        db.query(PayrollRun)
        .filter(PayrollRun.department == department, PayrollRun.cutoff_period == cutoff_period)
        .first()
    )
    if run:
        return run
    start, end = _period_dates(cutoff_period)
    run = PayrollRun(
        department=department,
        cutoff_period=cutoff_period,
        period_start=start,
        period_end=end,
        status="DRAFT",
        log="[]",
    )
    db.add(run)
    return run


def _log(db: Session, run: PayrollRun, action: str, user: User, note: str | None = None):
    entries = json.loads(run.log or "[]")
    entries.append(
        {
            "action": action,
            "status": run.status,
            "by": display_name(db.get(User, user.id)),
            "at": datetime.utcnow().isoformat(),
            "note": note,
        }
    )
    run.log = json.dumps(entries)


def _names(db: Session, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: display_name(u) for u in db.query(User).filter(User.id.in_(ids)).all()}


def _serialize(db: Session, run: PayrollRun | None, user: User, department: str, cutoff_period: str):
    can_prepare = can_payroll(db, user, PAYROLL_PREPARE)
    can_approve = can_payroll(db, user, PAYROLL_APPROVE)
    can_release = can_payroll(db, user, PAYROLL_RELEASE)
    can_contrib = can_payroll(db, user, PAYROLL_CONTRIBUTIONS)
    is_superadmin = _role(user) == "superadmin"
    status = run.status if run else "DRAFT"
    names = _names(
        db,
        [
            run.generated_by, run.submitted_by, run.approved_by, run.locked_by, run.paid_by,
            run.snapshot_by, run.reviewed_by, run.contributions_by,
        ]
        if run
        else [],
    )

    def stamp(prefix):
        if not run or not getattr(run, f"{prefix}_at"):
            return None
        return {
            "at": getattr(run, f"{prefix}_at").isoformat(),
            "by": names.get(getattr(run, f"{prefix}_by")),
        }

    return {
        "department": department,
        "cutoff_period": cutoff_period,
        "status": status,
        "employee_count": run.employee_count if run else 0,
        "total_gross": float(run.total_gross or 0) if run else 0,
        "total_net": float(run.total_net or 0) if run else 0,
        "generated": stamp("generated"),
        "submitted": stamp("submitted"),
        "reviewed": stamp("reviewed"),
        "contributions": stamp("contributions"),
        "approved": stamp("approved"),
        "locked": stamp("locked"),
        "paid": stamp("paid"),
        "return_note": run.return_note if run else None,
        "log": json.loads(run.log or "[]") if run else [],
        # Pay run: created on Pay Runs; the snapshot from Generate.
        "exists": run is not None,
        "has_snapshot": bool(run and run.snapshot),
        "snapshot_at": run.snapshot_at.isoformat() if run and run.snapshot_at else None,
        "snapshot_by": names.get(run.snapshot_by) if run else None,
        "precheck": json.loads(run.precheck) if run and run.precheck else None,
        "pay_date": run.pay_date.isoformat() if run and run.pay_date else None,
        # What this viewer may do next.
        # Generate + edit figures (deductions, OT) -- also gates the inputs.
        "can_generate": can_prepare and status in EDITABLE_STATUSES,
        "can_submit": can_prepare and status == "GENERATED",
        # For Review -> Contributions (the reviewer forwards it).
        "can_forward": can_approve and status == "FOR_REVIEW",
        # Contributions: edit SSS / PhilHealth / Pag-IBIG / tax only, then
        # send it to the head.
        "can_edit_contributions": can_contrib and status == "CONTRIBUTIONS",
        "can_submit_contributions": can_contrib and status == "CONTRIBUTIONS",
        "can_approve": can_approve and status == "HEAD_REVIEW",
        # Head sends it back to Contributions (not all the way back).
        "can_return_contributions": can_approve and status == "HEAD_REVIEW",
        "can_return": can_approve
        and status in ("FOR_REVIEW", "CONTRIBUTIONS", "HEAD_REVIEW", "APPROVED"),
        "can_lock": can_release and status == "APPROVED",
        "can_mark_paid": can_release and status == "LOCKED",
        "can_unlock": is_superadmin and status == "LOCKED",
        # This viewer's payroll steps, for the "waiting for ..." note.
        "my_steps": {
            "prepare": can_prepare,
            "approve": can_approve,
            "contributions": can_contrib,
            "release": can_release,
        },
    }


@router.get("")
def get_payroll_run(
    department: str = Query(...),
    cutoff_period: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    ensure_payroll_allowed(db, current_user, department)
    run = (
        db.query(PayrollRun)
        .filter(PayrollRun.department == department, PayrollRun.cutoff_period == cutoff_period)
        .first()
    )
    return _serialize(db, run, current_user, department, cutoff_period)


# =========================================================
# PAY RUNS -- one per payroll group + cutoff, created up front on the Pay
# Runs page (period + group), then opened to pre-check, generate (the
# snapshot) and move through approval.
# =========================================================
@router.get("/all")
def list_all_pay_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    """Every pay run, newest cutoff first (no snapshot)."""
    runs = db.query(PayrollRun).order_by(PayrollRun.period_end.desc(), PayrollRun.department).all()
    allowed = allowed_payroll_groups(db, current_user)
    if allowed is not None:
        runs = [run for run in runs if run.department in allowed]
    names = _names(db, [r.generated_by for r in runs])
    return [
        {
            "department": run.department,
            "cutoff_period": run.cutoff_period,
            "period_start": run.period_start.isoformat(),
            "period_end": run.period_end.isoformat(),
            "status": run.status,
            "pay_date": run.pay_date.isoformat() if run.pay_date else None,
            "employee_count": run.employee_count or 0,
            "total_gross": float(run.total_gross or 0),
            "total_net": float(run.total_net or 0),
            "generated_at": run.generated_at.isoformat() if run.generated_at else None,
            "generated_by": names.get(run.generated_by),
            "has_snapshot": bool(run.snapshot),
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }
        for run in runs
    ]


class CreateRunIn(BaseModel):
    department: str
    cutoff_period: str
    pay_date: date | None = None


def _not_sunday(day: date | None) -> date | None:
    """Paydays are Monday to Saturday: a Sunday moves to the Saturday before."""
    if day and day.weekday() == 6:
        return day - timedelta(days=1)
    return day


@router.post("/create")
def create_pay_run(
    payload: CreateRunIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """New pay run (Draft) for a payroll group + cutoff. One per pair --
    an existing one is reported, not duplicated."""
    ensure_can_payroll(db, current_user, PAYROLL_PREPARE)
    ensure_payroll_allowed(db, current_user, payload.department)
    exists = (
        db.query(PayrollRun.id)
        .filter(
            PayrollRun.department == payload.department,
            PayrollRun.cutoff_period == payload.cutoff_period,
        )
        .first()
    )
    if exists:
        raise HTTPException(
            status_code=409,
            detail="A pay run for this payroll group and cutoff is already created.",
        )
    run = _get_or_new(db, payload.department, payload.cutoff_period)
    run.pay_date = _not_sunday(payload.pay_date)
    _log(db, run, "created", current_user)
    db.commit()
    return _serialize(db, run, current_user, payload.department, payload.cutoff_period)


@router.get("/snapshot")
def get_pay_run_snapshot(
    department: str = Query(...),
    cutoff_period: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    """The rows saved at Generate ({rows, period, ...}), or null."""
    ensure_payroll_allowed(db, current_user, department)
    run = (
        db.query(PayrollRun)
        .filter(PayrollRun.department == department, PayrollRun.cutoff_period == cutoff_period)
        .first()
    )
    if not run or not run.snapshot:
        return None
    data = json.loads(run.snapshot)
    ids = allowed_employee_ids(db, current_user)
    if ids is not None and isinstance(data.get("rows"), list):
        data["rows"] = [
            r for r in data["rows"] if (r.get("employee") or {}).get("id") in ids
        ]
    return data


class PrecheckIn(BaseModel):
    start: date
    end: date
    employee_ids: list[int] = []
    # Trip-based (paid per trip, e.g. drivers): their time outs and face
    # review don't change their pay, so they're left out of those checks.
    trip_based_ids: list[int] = []


@router.post("/precheck")
def pay_run_precheck(
    payload: PrecheckIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    """What's still open for these employees in start..end before
    generating: missing time outs, attendance waiting for review, pending
    time corrections, overtime and leave not decided yet. (Days with no
    attendance and trips not cleared are worked out on the page.)"""
    from app.api.attendance import REVIEW_PENDING_STATUSES
    from app.models.attendance import AttendanceRecord
    from app.models.leave_request import LeaveRequest
    from app.models.overtime_request import OvertimeRequest
    from app.models.time_correction import TimeCorrectionRequest

    ids = set(payload.employee_ids or [])
    if not ids:
        return {"items": []}
    names = {
        e.id: f"{e.first_name} {e.last_name}"
        for e in db.query(Employee).filter(Employee.id.in_(ids))
    }

    def entry(employee_id, day, detail=None):
        return {"employee_id": employee_id, "name": names.get(employee_id), "date": str(day), "detail": detail}

    records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id.in_(ids),
            AttendanceRecord.attendance_date >= payload.start,
            AttendanceRecord.attendance_date <= payload.end,
        )
        .all()
    )
    today = datetime.utcnow().date()
    trip_based = set(payload.trip_based_ids or [])
    hourly = [r for r in records if r.employee_id not in trip_based]
    missing_out = [
        entry(r.employee_id, r.attendance_date, "Timed in, no time out")
        for r in hourly
        if r.check_in_time and not r.check_out_time and r.attendance_date < today
    ]
    review = [
        entry(r.employee_id, r.attendance_date, side_label)
        for r in hourly
        for side, side_label in (("time_in", "Time in"), ("time_out", "Time out"))
        if getattr(r, f"{side}_face_review_status") in REVIEW_PENDING_STATUSES
    ]
    corrections = [
        entry(t.employee_id, t.attendance_date, (t.reason or "")[:80])
        for t in db.query(TimeCorrectionRequest).filter(
            TimeCorrectionRequest.employee_id.in_(ids),
            TimeCorrectionRequest.status == "pending",
            TimeCorrectionRequest.attendance_date >= payload.start,
            TimeCorrectionRequest.attendance_date <= payload.end,
        )
    ]
    overtime = [
        entry(o.employee_id, o.ot_date, None)
        for o in db.query(OvertimeRequest).filter(
            OvertimeRequest.employee_id.in_(ids),
            OvertimeRequest.status == "pending",
            OvertimeRequest.ot_date >= payload.start,
            OvertimeRequest.ot_date <= payload.end,
        )
    ]
    leave = [
        entry(lr.employee_id, lr.start_date, f"{lr.start_date} to {lr.end_date}")
        for lr in db.query(LeaveRequest).filter(
            LeaveRequest.employee_id.in_(ids),
            LeaveRequest.status == "pending",
            LeaveRequest.start_date <= payload.end,
            LeaveRequest.end_date >= payload.start,
        )
    ]

    def item(key, label, rows, fix):
        rows = sorted(rows, key=lambda r: (r["date"], r["name"] or ""))
        return {"key": key, "label": label, "count": len(rows), "entries": rows[:100], "fix": fix}

    return {
        "items": [
            item("missing_time_out", "Missing time outs", missing_out, "/dashboard/attendance"),
            item("attendance_review", "Attendance waiting for review", review, "/dashboard/approvals?tab=attendance"),
            item("time_corrections", "Pending time corrections", corrections, "/dashboard/approvals?tab=attendance"),
            item("overtime", "Overtime not decided yet", overtime, "/dashboard/approvals?tab=overtime"),
            item("leave", "Leave not decided yet", leave, "/dashboard/approvals?tab=leave"),
        ]
    }


@router.get("/list")
def list_payroll_runs(
    department: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    """Status per cutoff, for labelling the period picker."""
    ensure_payroll_allowed(db, current_user, department)
    runs = db.query(PayrollRun).filter(PayrollRun.department == department).all()
    return {run.cutoff_period: run.status for run in runs}


class GenerateIn(BaseModel):
    department: str
    cutoff_period: str
    employee_count: int = 0
    total_gross: float = 0
    total_net: float = 0
    # Every employee's computed row as of now (PayrollList.jsx) -- saved
    # as the pay run snapshot. Older clients don't send it.
    snapshot: dict | None = None
    # Pre-check items still open, and the preparer's note for going ahead.
    precheck: dict | None = None


@router.post("/generate")
def mark_generated(
    payload: GenerateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_can_payroll(db, current_user, PAYROLL_PREPARE)
    ensure_payroll_allowed(db, current_user, payload.department)
    run = _get_or_new(db, payload.department, payload.cutoff_period)
    if run.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"This payroll is already {run.status.lower()} and can't be generated again.",
        )
    regenerated = run.status != "DRAFT"
    run.status = "GENERATED"
    run.employee_count = payload.employee_count
    run.total_gross = payload.total_gross
    run.total_net = payload.total_net
    run.generated_at = datetime.utcnow()
    run.generated_by = current_user.id
    if payload.snapshot is not None:
        run.snapshot = json.dumps(payload.snapshot, default=str)
        run.snapshot_at = run.generated_at
        run.snapshot_by = current_user.id
    open_items = [i for i in (payload.precheck or {}).get("items", []) if i.get("count")]
    run.precheck = json.dumps(
        {
            "items": open_items,
            "note": ((payload.precheck or {}).get("note") or "").strip()[:500] or None,
            "by": display_name(db.get(User, current_user.id)),
            "at": run.generated_at.isoformat(),
        }
    )
    _log(
        db,
        run,
        "regenerated" if regenerated else "generated",
        current_user,
        (
            "Generated with open pre-check items: "
            + ", ".join(f"{i.get('label')} ({i.get('count')})" for i in open_items)
            + (f". Note: {payload.precheck.get('note')}" if (payload.precheck or {}).get("note") else "")
        )[:500]
        if open_items
        else None,
    )
    db.commit()
    return _serialize(db, run, current_user, payload.department, payload.cutoff_period)


class TransitionIn(BaseModel):
    department: str
    cutoff_period: str
    action: str
    note: str | None = None


# action -> (allowed from, new status, who, timestamp prefix, note required)
TRANSITIONS = {
    "submit": (("GENERATED",), "FOR_REVIEW", PAYROLL_PREPARE, "submitted", False),
    "forward": (("FOR_REVIEW",), "CONTRIBUTIONS", PAYROLL_APPROVE, "reviewed", False),
    "submit_contributions": (
        ("CONTRIBUTIONS",), "HEAD_REVIEW", PAYROLL_CONTRIBUTIONS, "contributions", False,
    ),
    "return_contributions": (("HEAD_REVIEW",), "CONTRIBUTIONS", PAYROLL_APPROVE, None, True),
    "approve": (("HEAD_REVIEW",), "APPROVED", PAYROLL_APPROVE, "approved", False),
    "return": (
        ("FOR_REVIEW", "CONTRIBUTIONS", "HEAD_REVIEW", "APPROVED"),
        "GENERATED",
        PAYROLL_APPROVE,
        None,
        True,
    ),
    "lock": (("APPROVED",), "LOCKED", PAYROLL_RELEASE, "locked", False),
    "mark_paid": (("LOCKED",), "PAID", PAYROLL_RELEASE, "paid", False),
    "unlock": (("LOCKED",), "APPROVED", "superadmin", None, True),
}


class ContributionLineIn(BaseModel):
    employee_id: int
    segment: str = ""
    sssDeduction: float | None = None
    philhealthDeduction: float | None = None
    pagibigDeduction: float | None = None
    withholdingTax: float | None = None


class ContributionsIn(BaseModel):
    department: str
    cutoff_period: str
    lines: list[ContributionLineIn]


@router.post("/contributions")
def save_contributions(
    payload: ContributionsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Contributions step: change SSS / PhilHealth / Pag-IBIG / tax on the
    run's snapshot (everything else stays as generated). Net pay and total
    deductions move by the difference; the saved payroll_deductions row
    follows, so a later regenerate keeps the amounts."""
    from app.models.payroll_deductions import PayrollDeduction

    ensure_can_payroll(db, current_user, PAYROLL_CONTRIBUTIONS)
    ensure_payroll_allowed(db, current_user, payload.department)
    run = (
        db.query(PayrollRun)
        .filter(
            PayrollRun.department == payload.department,
            PayrollRun.cutoff_period == payload.cutoff_period,
        )
        .first()
    )
    if not run or run.status != "CONTRIBUTIONS":
        raise HTTPException(
            status_code=409,
            detail="Government contributions can only be changed at the Contributions step.",
        )
    if not run.snapshot:
        raise HTTPException(
            status_code=409,
            detail="This pay run has no snapshot -- return it and generate it again first.",
        )
    data = json.loads(run.snapshot)
    rows = data.get("rows") or []

    def key(row):
        emp = row.get("employee") or {}
        return (emp.get("id"), (emp.get("_segment") or {}).get("key") or "")

    by_key = {key(r): r for r in rows}
    changed = []
    for line in payload.lines:
        row = by_key.get((line.employee_id, line.segment or ""))
        if row is None:
            continue
        old = sum(float(row.get(f) or 0) for f in GOV_FIELDS)
        for field in GOV_FIELDS:
            value = getattr(line, field)
            if value is not None:
                if value < 0:
                    raise HTTPException(status_code=400, detail="Amounts can't be negative.")
                row[field] = round(value, 2)
        delta = round(sum(float(row.get(f) or 0) for f in GOV_FIELDS) - old, 2)
        if not delta and not any(getattr(line, f) is not None for f in GOV_FIELDS):
            continue
        row["netPay"] = round(float(row.get("netPay") or 0) - delta, 2)
        row["totalDeductions"] = round(float(row.get("totalDeductions") or 0) + delta, 2)
        row["contributionsEdited"] = True
        changed.append(row)

        saved = (
            db.query(PayrollDeduction)
            .filter(
                PayrollDeduction.employee_id == line.employee_id,
                PayrollDeduction.cutoff_period == payload.cutoff_period,
                PayrollDeduction.department == payload.department,
                PayrollDeduction.segment == (line.segment or ""),
            )
            .first()
        )
        if saved is not None:
            for field, column in GOV_FIELDS.items():
                setattr(saved, column, row.get(field) or 0)
            saved.net_pay = row["netPay"]

    run.snapshot = json.dumps(data, default=str)
    run.total_net = round(sum(float(r.get("netPay") or 0) for r in rows), 2)
    if changed:
        names = ", ".join(
            f"{(r.get('employee') or {}).get('first_name', '')} {(r.get('employee') or {}).get('last_name', '')}".strip()
            for r in changed[:5]
        )
        more = f" and {len(changed) - 5} more" if len(changed) > 5 else ""
        _log(db, run, "contributions_edited", current_user, f"{names}{more}"[:500])
    db.commit()
    return {
        "run": _serialize(db, run, current_user, payload.department, payload.cutoff_period),
        "changed": len(changed),
    }


@router.post("/transition")
def transition_payroll_run(
    payload: TransitionIn,
    db: Session = Depends(get_db),
    # Not _require_payroll: a Finance approver may have Payroll view-only
    # plus "Approve & Return" -- the step grant below is what counts.
    current_user: User = Depends(get_current_user),
):
    if payload.action not in TRANSITIONS:
        raise HTTPException(status_code=400, detail="Unknown action.")
    allowed_from, new_status, who, stamp, needs_note = TRANSITIONS[payload.action]

    if who != "superadmin":
        ensure_can_payroll(db, current_user, who)
    if who == "superadmin" and _role(current_user) != "superadmin":
        raise HTTPException(status_code=403, detail="Only a superadmin can unlock payroll.")

    ensure_payroll_allowed(db, current_user, payload.department)
    note = (payload.note or "").strip() or None
    if needs_note and not note:
        raise HTTPException(status_code=400, detail="Please give a reason.")

    run = _get_or_new(db, payload.department, payload.cutoff_period)
    if run.status not in allowed_from:
        raise HTTPException(
            status_code=409,
            detail=f"Payroll is {run.status.replace('_', ' ').lower()}; it can't be moved that way.",
        )

    run.status = new_status
    if stamp:
        setattr(run, f"{stamp}_at", datetime.utcnow())
        setattr(run, f"{stamp}_by", current_user.id)
    if payload.action == "return_contributions":
        run.return_note = note
        run.contributions_at = run.contributions_by = None
    if payload.action in ("return", "unlock"):
        run.return_note = note
        if payload.action == "return":
            run.submitted_at = run.submitted_by = None
            run.reviewed_at = run.reviewed_by = None
            run.contributions_at = run.contributions_by = None
            run.approved_at = run.approved_by = None
        else:
            run.locked_at = run.locked_by = None
            # Its figures can change again, so its released payslips are
            # taken back until it's locked and released again.
            recalled = (
                db.query(PayslipRelease)
                .filter(
                    PayslipRelease.department == run.department,
                    PayslipRelease.cutoff_period == run.cutoff_period,
                )
                .delete(synchronize_session=False)
            )
            if recalled:
                plural = "s" if recalled != 1 else ""
                note = f"{note} ({recalled} released payslip{plural} taken back)"
    _log(db, run, payload.action, current_user, note)
    db.commit()
    return _serialize(db, run, current_user, payload.department, payload.cutoff_period)


# =========================================================
# LOCKED PAYROLLS + RELEASE PAYSLIP
# =========================================================
RELEASABLE_STATUSES = ("LOCKED", "PAID")


@router.get("/locked")
def list_locked_payrolls(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    """Every Locked / Paid payroll (all groups, and departments from
    before groups), newest cutoff first, with how many payslips are
    released."""
    runs = (
        db.query(PayrollRun)
        .filter(PayrollRun.status.in_(RELEASABLE_STATUSES))
        .order_by(PayrollRun.period_end.desc(), PayrollRun.department)
        .all()
    )
    allowed = allowed_payroll_groups(db, current_user)
    if allowed is not None:
        runs = [run for run in runs if run.department in allowed]
    released = {}
    for dept, cutoff in db.query(PayslipRelease.department, PayslipRelease.cutoff_period):
        released[(dept, cutoff)] = released.get((dept, cutoff), 0) + 1
    names = _names(db, [r.locked_by for r in runs] + [r.paid_by for r in runs])
    return [
        {
            "department": run.department,
            "cutoff_period": run.cutoff_period,
            "period_start": run.period_start.isoformat(),
            "period_end": run.period_end.isoformat(),
            "status": run.status,
            "employee_count": run.employee_count or 0,
            "total_gross": float(run.total_gross or 0),
            "total_net": float(run.total_net or 0),
            "locked_at": run.locked_at.isoformat() if run.locked_at else None,
            "locked_by": names.get(run.locked_by),
            "paid_at": run.paid_at.isoformat() if run.paid_at else None,
            "paid_by": names.get(run.paid_by),
            "released_count": released.get((run.department, run.cutoff_period), 0),
        }
        for run in runs
    ]


@router.get("/releases")
def list_payslip_releases(
    department: str = Query(...),
    cutoff_period: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    """Released payslips of one payroll, keyed "employee id|segment"."""
    ensure_payroll_allowed(db, current_user, department)
    rows = (
        db.query(PayslipRelease)
        .filter(
            PayslipRelease.department == department,
            PayslipRelease.cutoff_period == cutoff_period,
        )
        .all()
    )
    names = _names(db, [r.released_by for r in rows])
    return {
        f"{r.employee_id}|{r.segment}": {
            "released_at": r.released_at.isoformat() if r.released_at else None,
            "released_by": names.get(r.released_by),
        }
        for r in rows
    }


class ReleaseIn(BaseModel):
    department: str
    cutoff_period: str
    employee_id: int
    segment: str = ""
    payout_date: str | None = None
    gross_pay: float = 0
    net_pay: float = 0
    # The payslip as Payroll has it (PayslipModal's row + period).
    snapshot: dict


@router.post("/release-payslip")
def release_payslip(
    payload: ReleaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Release (or re-release) one employee's payslip -- Lock & Mark Paid
    step, and only once the payroll is Locked / Paid."""
    ensure_can_payroll(db, current_user, PAYROLL_RELEASE)
    ensure_payroll_allowed(db, current_user, payload.department)
    run = (
        db.query(PayrollRun)
        .filter(
            PayrollRun.department == payload.department,
            PayrollRun.cutoff_period == payload.cutoff_period,
        )
        .first()
    )
    if not run or run.status not in RELEASABLE_STATUSES:
        raise HTTPException(
            status_code=409, detail="Payslips can be released only after the payroll is locked."
        )
    if not db.query(Employee.id).filter(Employee.id == payload.employee_id).first():
        raise HTTPException(status_code=404, detail="Employee not found.")
    segment = (payload.segment or "")[:20]
    release = (
        db.query(PayslipRelease)
        .filter(
            PayslipRelease.employee_id == payload.employee_id,
            PayslipRelease.department == payload.department,
            PayslipRelease.cutoff_period == payload.cutoff_period,
            PayslipRelease.segment == segment,
        )
        .first()
    )
    if release is None:
        release = PayslipRelease(
            employee_id=payload.employee_id,
            department=payload.department,
            cutoff_period=payload.cutoff_period,
            segment=segment,
        )
        db.add(release)
    release.period_start = run.period_start
    release.period_end = run.period_end
    release.payout_date = (payload.payout_date or "")[:20] or None
    release.gross_pay = payload.gross_pay
    release.net_pay = payload.net_pay
    release.snapshot = json.dumps(payload.snapshot)
    release.released_at = datetime.utcnow()
    release.released_by = current_user.id
    db.commit()
    return {
        "key": f"{release.employee_id}|{release.segment}",
        "released_at": release.released_at.isoformat(),
        "released_by": display_name(db.get(User, current_user.id)),
    }


def _my_release(release: PayslipRelease, with_snapshot: bool = False) -> dict:
    data = {
        "id": release.id,
        "payroll": release.department,
        "cutoff_period": release.cutoff_period,
        "period_start": release.period_start.isoformat(),
        "period_end": release.period_end.isoformat(),
        "payout_date": release.payout_date,
        "gross_pay": float(release.gross_pay or 0),
        "net_pay": float(release.net_pay or 0),
        "released_at": release.released_at.isoformat() if release.released_at else None,
    }
    if with_snapshot:
        data["snapshot"] = json.loads(release.snapshot or "{}")
    return data


@router.get("/my-payslips")
def my_payslips(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The logged-in employee's released payslips, newest first."""
    if not current_user.employee_id:
        return []
    rows = (
        db.query(PayslipRelease)
        .filter(PayslipRelease.employee_id == current_user.employee_id)
        .order_by(PayslipRelease.period_end.desc(), PayslipRelease.segment.desc())
        .all()
    )
    return [_my_release(r) for r in rows]


@router.get("/my-payslips/{release_id}")
def my_payslip(
    release_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    release = db.get(PayslipRelease, release_id)
    if not release or release.employee_id != current_user.employee_id:
        raise HTTPException(status_code=404, detail="Payslip not found.")
    return _my_release(release, with_snapshot=True)


# =========================================================
# TRIP CHECK -- every trip a driver / helper did in the cutoff, whatever
# its status, so Payroll sees the ones not paid yet (still waiting for
# an approval, or no attendance that day) next to the paid ones.
# Payroll pays a trip only when it's COMPLETED (Finance approved) and
# there's an attendance record on its day (PayrollList.jsx).
# =========================================================
PAID_TRIP_STATUSES = {"COMPLETED", "APPROVED"}

# Trip documents (photos) the Trip Document step checks, in order.
TRIP_DOCUMENTS = (
    ("INVOICE_PHOTO", "Invoice"),
    ("LM_MANIFEST_PHOTO", "LM"),
    ("LM_CHECKOUT_STAMPED_PHOTO", "Stamped LM (checkout)"),
    ("STAMPED_INVOICE_PHOTO", "Stamped Invoice"),
)
# Status -> (step, Org Chart approval kind, who it falls to when nobody
# on the chart has that step ticked).
TRIP_STEPS = {
    "ASSIGNED": ("Not started", None, "Driver"),
    "ACTIVE": ("In progress", None, "Driver"),
    "PENDING_MANUAL_APPROVAL": ("Manual entry", None, "Superadmin"),
    "PENDING_APPROVAL": ("Trip Approvals", "trip_coordinator", "Coordinator admin"),
    "PENDING_OFFICE_REVIEW": ("Trip Document", "trip_office", "Office"),
    "PENDING_FINANCE_REVIEW": ("Finance Trips", "trip_finance", "Finance"),
}


def _trip_followups(db: Session, trips: list) -> dict:
    """{trip_id: {"step", "responsible", "missing_docs"}} for the trips not
    completed yet: the Org Chart approver at the trip's current step (by
    its driver, same as "For me" on those pages), or the coordinator a
    returned trip was handed to; plus the missing photos while it's in
    Trip Document."""
    from app.models.files import File
    from app.models.org_unit import OrgUnit
    from app.models.trip_finance_review import TripFinanceReview
    from app.services.approval_chain import effective_step, resolve_chain

    open_trips = [
        t for t in trips if getattr(t.status, "value", t.status) in TRIP_STEPS
    ]
    if not open_trips:
        return {}
    ids = [t.id for t in open_trips]
    reviews = {
        r.trip_id: r
        for r in db.query(TripFinanceReview).filter(TripFinanceReview.trip_id.in_(ids))
    }
    docs: dict = {}
    for trip_id, doc_type in db.query(File.entity_id, File.document_type).filter(
        File.entity_type == "trip", File.entity_id.in_(ids)
    ):
        docs.setdefault(trip_id, set()).add(doc_type)

    units = db.query(OrgUnit).all()
    approver_cache: dict = {}
    user_ids: set = set()
    picked: dict = {}
    for trip in open_trips:
        status = getattr(trip.status, "value", trip.status)
        step, kind, fallback = TRIP_STEPS[status]
        review = reviews.get(trip.id)
        who_id = None
        if status in ("ASSIGNED", "ACTIVE"):
            who_id = trip.driver_id
        elif review is not None and review.resolver_user_id and not review.resolved_at:
            who_id = review.resolver_user_id  # handed to a coordinator to fix
        elif kind:
            key = (trip.driver_id, kind)
            if key not in approver_cache:
                driver = trip.driver
                chain = resolve_chain(db, driver.employee, driver, kind, units) if driver else []
                approver_cache[key] = chain[effective_step(db, chain, 0)[0]] if chain else None
            who_id = approver_cache[key]
        if who_id:
            user_ids.add(who_id)
        picked[trip.id] = (step, who_id, fallback, status)

    names = _names(db, user_ids)
    out = {}
    for trip_id, (step, who_id, fallback, status) in picked.items():
        have = docs.get(trip_id, set())
        out[trip_id] = {
            "step": step,
            "responsible": names.get(who_id) or fallback,
            "responsible_is_person": bool(who_id and names.get(who_id)),
            "missing_docs": (
                [label for doc_type, label in TRIP_DOCUMENTS if doc_type not in have]
                if status == "PENDING_OFFICE_REVIEW"
                else []
            ),
        }
    return out


@router.get("/trip-check")
def get_trip_check(
    start: date,
    end: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    from datetime import time, timedelta

    import pytz
    from sqlalchemy.orm import joinedload

    from app.models.attendance import AttendanceRecord
    from app.models.trip_helper import TripHelper
    from app.models.trips import Trip
    from app.services.trip_rates import category_label, load_rules, resolve_trip_rates
    from app.utils.timezone import utc_to_ph_date

    ph = pytz.timezone("Asia/Manila")
    utc_from = ph.localize(datetime.combine(start, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
    utc_to = ph.localize(datetime.combine(end + timedelta(days=1), time.min)).astimezone(pytz.utc).replace(tzinfo=None)

    trips = (
        db.query(Trip)
        .options(joinedload(Trip.vehicle_unit), joinedload(Trip.trip_rate_profile))
        .filter(
            Trip.start_time >= utc_from,
            Trip.start_time < utc_to,
            Trip.status != "CANCELLED",
            Trip.is_archived.is_(False),
        )
        .all()
    )
    # (No early return: manual route rides count even without trips.)

    trip_ids = [t.id for t in trips]
    driver_employee = dict(
        db.query(User.id, User.employee_id).filter(
            User.id.in_({t.driver_id for t in trips if t.driver_id})
        )
    )
    helpers = {}
    for trip_id, helper_id in db.query(TripHelper.trip_id, TripHelper.helper_id).filter(
        TripHelper.trip_id.in_(trip_ids)
    ):
        helpers.setdefault(trip_id, []).append(helper_id)

    people = []  # (trip, employee_id, role)
    for trip in trips:
        if driver_employee.get(trip.driver_id):
            people.append((trip, driver_employee[trip.driver_id], "driver"))
        for helper_id in helpers.get(trip.id, []):
            people.append((trip, helper_id, "helper"))

    attended = {
        (employee_id, day)
        for employee_id, day in db.query(
            AttendanceRecord.employee_id, AttendanceRecord.attendance_date
        ).filter(
            AttendanceRecord.employee_id.in_({p[1] for p in people}),
            AttendanceRecord.attendance_date.between(start, end),
        )
    }
    rules = load_rules(db)
    followup = _trip_followups(db, trips)

    rows = []
    for trip, employee_id, role in people:
        day = utc_to_ph_date(trip.start_time)
        status = getattr(trip.status, "value", trip.status)
        rates = resolve_trip_rates(trip, day, rules)
        has_attendance = (employee_id, day) in attended
        rows.append(
            {
                "trip_id": trip.id,
                "employee_id": employee_id,
                "role": role,
                "date": str(day),
                "ticket_no": trip.ticket_no,
                "status": status,
                "vehicle_unit": trip.vehicle_unit.unit_code if trip.vehicle_unit else None,
                "plate_number": trip.vehicle_unit.plate_number if trip.vehicle_unit else None,
                "trip_rate_profile": category_label(trip),
                "first_trip_rate": rates[f"{role}_first_trip_rate"],
                "has_attendance": has_attendance,
                "counted": status in PAID_TRIP_STATUSES and has_attendance,
                # Not completed yet: who it's waiting on, and (Trip
                # Document) which photos are still missing.
                **followup.get(trip.id, {}),
            }
        )
    # Route rides (assigned on these trips, or manual in the period).
    from app.models.route_ride import RouteRide
    from app.services.route_ride import ride_amount, ride_day, ride_rates

    rider_employee = dict(
        db.query(User.id, User.employee_id).filter(
            User.id.in_({r.rider_user_id for r in db.query(RouteRide.rider_user_id)})
        )
    )
    for ride in db.query(RouteRide).options(joinedload(RouteRide.trip)).all():
        employee_id = rider_employee.get(ride.rider_user_id)
        day = ride_day(ride)
        if not employee_id or day is None or not (start <= day <= end):
            continue
        trip = ride.trip
        status = getattr(trip.status, "value", trip.status) if trip else "MANUAL"
        if trip is not None and (status == "CANCELLED" or trip.is_archived):
            continue
        has_attendance = (employee_id, day) in attended or bool(
            db.query(AttendanceRecord.id)
            .filter(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.attendance_date == day,
            )
            .first()
        )
        rows.append(
            {
                "trip_id": trip.id if trip else None,
                "route_ride_id": ride.id,
                "employee_id": employee_id,
                "role": "route_rider",
                "date": str(day),
                "ticket_no": trip.ticket_no if trip else f"Route ride (manual) x{ride.quantity or 1}",
                "status": status,
                "vehicle_unit": trip.vehicle_unit.unit_code if trip and trip.vehicle_unit else None,
                "plate_number": trip.vehicle_unit.plate_number if trip and trip.vehicle_unit else None,
                "trip_rate_profile": (
                    trip.trip_rate_profile.profile_name
                    if trip and trip.trip_rate_profile
                    else (ride.trip_rate_profile.profile_name if ride.trip_rate_profile else None)
                ),
                "first_trip_rate": round(ride_amount(ride, rules), 2),
                "has_attendance": has_attendance,
                # Manual route rides are entered by an admin and trip-based:
                # paid without attendance. A ride on a real trip still needs
                # the trip completed and attendance that day.
                "counted": trip is None or (status in PAID_TRIP_STATUSES and has_attendance),
                # What payroll needs to pay a manual ride (no attendance
                # record to carry its tickets on).
                **(
                    {
                        "quantity": ride.quantity or 1,
                        "driver_first_trip_rate": ride_rates(ride, rules)["first"],
                        "driver_next_trip_rate": ride_rates(ride, rules)["next"],
                        "route_ride_amount": ride_rates(ride, rules)["fixed"],
                    }
                    if trip is None
                    else {}
                ),
            }
        )

    rows.sort(key=lambda r: (r["date"], r["trip_id"] or 0))
    ids = allowed_employee_ids(db, current_user)
    if ids is not None:
        rows = [r for r in rows if r.get("employee_id") in ids]
    return rows


# =========================================================
# WORK HISTORY SPLITS -- an employee whose department / pay changed inside
# the cutoff (201 -> Work History) is paid per part: each part in the
# department and at the pay in effect then. Government contributions and
# cash advance are taken once, in the last part (is_last).
# =========================================================
@router.get("/job-segments")
def get_job_segments(
    start: date,
    end: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_payroll),
):
    from app.services.job_history import apply_due_changes, segments

    apply_due_changes(db)
    ids = allowed_employee_ids(db, current_user)
    return {
        str(emp): spans
        for emp, spans in segments(db, start, end).items()
        if ids is None or emp in ids
    }
