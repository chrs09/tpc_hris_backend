# app/api/payroll/incentive_runs.py
#
# Incentive Runs: incentives paid out apart from payroll, with their own
# approval and a permanent history. See app/services/incentive_runs.py.
# Steps use the payroll ones on the Org Chart (Prepare & Submit / Approve
# & Return / Lock & Mark Paid = Release); superadmin can do all.

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role_or_module
from app.models.employees import Employee
from app.models.incentive_program import IncentiveProgram
from app.models.incentive_run import IncentiveRun, IncentiveRunLine
from app.models.user import User
from app.services.incentive_runs import (
    EDITABLE,
    PAID_OUT,
    RunError,
    generate,
    payroll_totals,
    program_ids,
    retotal,
    serialize_line,
    snapshot,
)
from app.services.incentives import RELEASE_METHODS
from app.services.payroll_lock import (
    PAYROLL_APPROVE,
    PAYROLL_PREPARE,
    PAYROLL_RELEASE,
    can_payroll,
    ensure_can_payroll,
)
from app.utils.user_display import display_name

router = APIRouter(prefix="/incentive-runs", tags=["Incentive Runs"])

_require_view = require_role_or_module(
    roles=["admin", "payroll_admin"],
    module_key=["payroll.incentive_policies", "payroll.payroll"],
)

STATUSES = ("DRAFT", "GENERATED", "FOR_REVIEW", "APPROVED", "RELEASED", "CANCELLED")

# action -> (allowed from, new status, payroll step, timestamp prefix, note required)
TRANSITIONS = {
    "submit": (("GENERATED",), "FOR_REVIEW", PAYROLL_PREPARE, "submitted", False),
    "approve": (("FOR_REVIEW",), "APPROVED", PAYROLL_APPROVE, "approved", False),
    "return": (("FOR_REVIEW", "APPROVED"), "GENERATED", PAYROLL_APPROVE, None, True),
    "release": (("APPROVED",), "RELEASED", PAYROLL_RELEASE, "released", False),
    "cancel": (("DRAFT", "GENERATED", "FOR_REVIEW", "APPROVED"), "CANCELLED", PAYROLL_PREPARE, "cancelled", True),
}


class RunIn(BaseModel):
    name: str
    period_start: date
    period_end: date
    program_ids: list[int]
    release_method: str = "cash"
    payroll_date: date | None = None
    notes: str | None = None


class AdjustmentIn(BaseModel):
    employee_id: int
    amount: float
    note: str


class TransitionIn(BaseModel):
    action: str
    note: str | None = None
    reference: str | None = None
    released_on: date | None = None


def _log(db: Session, run: IncentiveRun, action: str, user: User, note: str | None = None):
    entries = json.loads(run.log or "[]")
    entries.append({
        "action": action,
        "status": run.status,
        "by": display_name(db.get(User, user.id)),
        "at": datetime.utcnow().isoformat() + "+00:00",
        "note": note,
    })
    run.log = json.dumps(entries)


def _utc(value):
    """Stored times are naive UTC -- mark them so the browser shows PH time."""
    return value.isoformat() + "+00:00" if value else None


def _get(db: Session, run_id: int) -> IncentiveRun:
    run = (
        db.query(IncentiveRun)
        .options(joinedload(IncentiveRun.lines))
        .filter(IncentiveRun.id == run_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Incentive run not found.")
    return run


def _serialize(db: Session, run: IncentiveRun, user: User, with_lines: bool = False) -> dict:
    ids = program_ids(run)
    frozen = snapshot(run)
    names = {p["id"]: p["name"] for p in frozen}
    missing = [i for i in ids if i not in names]
    if missing:
        for p in db.query(IncentiveProgram).filter(IncentiveProgram.id.in_(missing)):
            names[p.id] = p.name
    people = {
        u.id: display_name(u)
        for u in db.query(User).filter(
            User.id.in_({
                uid for uid in (run.generated_by, run.submitted_by, run.approved_by, run.released_by)
                if uid
            } or {0})
        )
    }
    prepare = can_payroll(db, user, PAYROLL_PREPARE)
    approve = can_payroll(db, user, PAYROLL_APPROVE)
    release = can_payroll(db, user, PAYROLL_RELEASE)
    data = {
        "id": run.id,
        "name": run.name,
        "period_start": run.period_start,
        "period_end": run.period_end,
        "program_ids": ids,
        "programs": [{"id": i, "name": names.get(i, f"Program #{i}")} for i in ids],
        "release_method": run.release_method,
        "payroll_date": run.payroll_date,
        "status": run.status,
        "notes": run.notes,
        "return_note": run.return_note,
        "total": float(run.total or 0),
        "employee_count": run.employee_count,
        "release_reference": run.release_reference,
        "released_on": run.released_on,
        "generated": {"at": _utc(run.generated_at), "by": people.get(run.generated_by)} if run.generated_at else None,
        "approved": {"at": _utc(run.approved_at), "by": people.get(run.approved_by)} if run.approved_at else None,
        "released": {"at": _utc(run.released_at), "by": people.get(run.released_by)} if run.released_at else None,
        "log": json.loads(run.log or "[]"),
        "can_edit": prepare and run.status in EDITABLE,
        "can_generate": prepare and run.status in EDITABLE,
        "can_submit": prepare and run.status == "GENERATED" and bool(run.lines),
        "can_approve": approve and run.status == "FOR_REVIEW",
        "can_return": approve and run.status in ("FOR_REVIEW", "APPROVED"),
        "can_release": release and run.status == "APPROVED",
        "can_cancel": prepare and run.status in TRANSITIONS["cancel"][0],
    }
    if with_lines:
        data["frozen_programs"] = frozen
        data["lines"] = [serialize_line(line) for line in run.lines]
    return data


def _apply(db: Session, run: IncentiveRun, data: RunIn) -> None:
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Give the run a name.")
    if data.period_end < data.period_start:
        raise HTTPException(status_code=400, detail="Period end can't be before its start.")
    ids = sorted(set(data.program_ids))
    if not ids:
        raise HTTPException(status_code=400, detail="Pick at least one incentive program.")
    if db.query(IncentiveProgram.id).filter(IncentiveProgram.id.in_(ids)).count() != len(ids):
        raise HTTPException(status_code=400, detail="Unknown incentive program.")
    if data.release_method not in RELEASE_METHODS:
        raise HTTPException(status_code=400, detail="Release method must be cash, payroll or bank.")
    if data.release_method == "payroll" and not data.payroll_date:
        raise HTTPException(
            status_code=400,
            detail="Pick the payroll date -- the run shows on the cutoff that covers it.",
        )
    run.name = name[:150]
    run.period_start = data.period_start
    run.period_end = data.period_end
    run.program_ids = json.dumps(ids)
    run.release_method = data.release_method
    run.payroll_date = data.payroll_date if data.release_method == "payroll" else None
    run.notes = (data.notes or "").strip() or None


# ---------------------------------------------------------------- reads


@router.get("")
def list_runs(
    status: str | None = Query(None),
    year: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    q = db.query(IncentiveRun)
    if status:
        q = q.filter(IncentiveRun.status == status)
    if year:
        q = q.filter(IncentiveRun.period_start <= date(year, 12, 31), IncentiveRun.period_end >= date(year, 1, 1))
    runs = q.order_by(IncentiveRun.period_start.desc(), IncentiveRun.id.desc()).all()
    return [_serialize(db, run, current_user) for run in runs]


@router.get("/history")
def incentive_history(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    status: str = Query("paid", description="paid (approved + released), released, approved or all"),
    program_id: int | None = Query(None),
    employee_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    """Every incentive line of approved / released runs (the transaction
    history), newest run first. Dates filter on the run's period."""
    statuses = {
        "paid": PAID_OUT,
        "released": ("RELEASED",),
        "approved": ("APPROVED",),
        "all": ("GENERATED", "FOR_REVIEW", "APPROVED", "RELEASED"),
    }.get(status, PAID_OUT)
    q = (
        db.query(IncentiveRunLine, IncentiveRun)
        .join(IncentiveRun, IncentiveRun.id == IncentiveRunLine.run_id)
        .filter(IncentiveRun.status.in_(statuses))
    )
    if date_from:
        q = q.filter(IncentiveRun.period_end >= date_from)
    if date_to:
        q = q.filter(IncentiveRun.period_start <= date_to)
    if program_id:
        q = q.filter(IncentiveRunLine.program_id == program_id)
    if employee_id:
        q = q.filter(IncentiveRunLine.employee_id == employee_id)
    rows = q.order_by(IncentiveRun.period_start.desc(), IncentiveRun.id.desc(), IncentiveRunLine.employee_name).all()
    return [
        {
            **serialize_line(line, with_details=False),
            "run_id": run.id,
            "run_name": run.name,
            "period_start": run.period_start,
            "period_end": run.period_end,
            "status": run.status,
            "release_method": run.release_method,
            "payroll_date": run.payroll_date,
            "released_on": run.released_on,
            "release_reference": run.release_reference,
        }
        for line, run in rows
    ]


@router.get("/payroll")
def incentives_for_payroll(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    """Approved / released "with payroll" runs for the cutoff, by employee
    id -- the Payroll page's separate Incentives column."""
    return payroll_totals(db, start, end)


@router.get("/{run_id}")
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    return _serialize(db, _get(db, run_id), current_user, with_lines=True)


# ---------------------------------------------------------------- changes


@router.post("")
def create_run(
    data: RunIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_can_payroll(db, current_user, PAYROLL_PREPARE)
    run = IncentiveRun(status="DRAFT", created_by=current_user.id)
    _apply(db, run, data)
    db.add(run)
    db.flush()
    _log(db, run, "created", current_user)
    db.commit()
    return _serialize(db, _get(db, run.id), current_user, with_lines=True)


@router.put("/{run_id}")
def update_run(
    run_id: int,
    data: RunIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_can_payroll(db, current_user, PAYROLL_PREPARE)
    run = _get(db, run_id)
    if run.status not in EDITABLE:
        raise HTTPException(status_code=409, detail=f"This run is {run.status.lower()} and can't be changed.")
    _apply(db, run, data)
    _log(db, run, "edited", current_user)
    db.commit()
    return _serialize(db, _get(db, run.id), current_user, with_lines=True)


@router.post("/{run_id}/generate")
def generate_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_can_payroll(db, current_user, PAYROLL_PREPARE)
    run = _get(db, run_id)
    regenerated = run.status == "GENERATED"
    try:
        generate(db, run, current_user.id)
    except RunError as e:
        raise HTTPException(status_code=409, detail=str(e))
    _log(db, run, "regenerated" if regenerated else "generated", current_user)
    db.commit()
    return _serialize(db, _get(db, run.id), current_user, with_lines=True)


@router.post("/{run_id}/adjustments")
def add_adjustment(
    run_id: int,
    data: AdjustmentIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A manual + / - line (e.g. a correction of an earlier released run)."""
    ensure_can_payroll(db, current_user, PAYROLL_PREPARE)
    run = _get(db, run_id)
    if run.status != "GENERATED":
        raise HTTPException(status_code=409, detail="Adjustments can only be added to a generated run.")
    if not data.amount:
        raise HTTPException(status_code=400, detail="Enter an amount (negative to deduct).")
    note = data.note.strip()
    if not note:
        raise HTTPException(status_code=400, detail="Give a reason for the adjustment.")
    employee = db.query(Employee).filter(Employee.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found.")
    run.lines.append(
        IncentiveRunLine(
            employee_id=employee.id,
            employee_name=" ".join(p for p in (employee.first_name, employee.last_name, employee.suffix) if p),
            department=employee.department,
            program_id=None,
            program_name="Adjustment",
            rule_type="adjustment",
            amount=round(data.amount, 2),
            is_adjustment=True,
            note=note[:500],
            created_by=current_user.id,
            created_at=datetime.utcnow(),
        )
    )
    retotal(run)
    _log(db, run, "adjusted", current_user, f"{employee.first_name} {employee.last_name}: {data.amount:+.2f} ({note})")
    db.commit()
    return _serialize(db, _get(db, run.id), current_user, with_lines=True)


@router.delete("/{run_id}/adjustments/{line_id}")
def delete_adjustment(
    run_id: int,
    line_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_can_payroll(db, current_user, PAYROLL_PREPARE)
    run = _get(db, run_id)
    if run.status != "GENERATED":
        raise HTTPException(status_code=409, detail="This run can't be changed now.")
    line = next((ln for ln in run.lines if ln.id == line_id and ln.is_adjustment), None)
    if not line:
        raise HTTPException(status_code=404, detail="Adjustment not found.")
    run.lines.remove(line)
    retotal(run)
    _log(db, run, "adjustment removed", current_user, f"{line.employee_name}: {float(line.amount):+.2f}")
    db.commit()
    return _serialize(db, _get(db, run.id), current_user, with_lines=True)


@router.post("/{run_id}/transition")
def transition_run(
    run_id: int,
    data: TransitionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.action not in TRANSITIONS:
        raise HTTPException(status_code=400, detail="Unknown action.")
    allowed_from, new_status, step, stamp, needs_note = TRANSITIONS[data.action]
    ensure_can_payroll(db, current_user, step)
    note = (data.note or "").strip() or None
    if needs_note and not note:
        raise HTTPException(status_code=400, detail="Please give a reason.")

    run = _get(db, run_id)
    if run.status not in allowed_from:
        raise HTTPException(
            status_code=409,
            detail=f"This run is {run.status.replace('_', ' ').lower()}; it can't be moved that way.",
        )
    if data.action == "submit" and not run.lines:
        raise HTTPException(status_code=400, detail="Nothing to submit -- the run has no lines.")

    run.status = new_status
    if stamp:
        setattr(run, f"{stamp}_at", datetime.utcnow())
        setattr(run, f"{stamp}_by", current_user.id)
    if data.action == "return":
        run.return_note = note
        run.submitted_at = run.submitted_by = None
        run.approved_at = run.approved_by = None
    if data.action == "release":
        run.release_reference = (data.reference or "").strip()[:100] or None
        run.released_on = data.released_on or date.today()
    _log(db, run, data.action, current_user, note or data.reference)
    db.commit()
    return _serialize(db, _get(db, run.id), current_user, with_lines=True)
