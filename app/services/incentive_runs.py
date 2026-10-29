# app/services/incentive_runs.py
#
# Incentive Runs: paying incentives out apart from payroll.
#   Generate  -- freezes the picked programs' settings into the run and
#                computes each one over the run's period (clipped to the
#                program's own period), one line per person per program.
#                Manual adjustments are kept across regenerates.
#   Approve / Release -- same Org Chart steps as payroll. Released is the
#                permanent record (Incentive History).
# Payroll only shows APPROVED / RELEASED "payroll" runs as a separate line
# after net pay, on the cutoff that covers the run's payroll_date.

import json
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.incentive_program import IncentiveProgram
from app.models.incentive_run import IncentiveRun, IncentiveRunLine
from app.services.incentives import RULE_TYPES, compute_program, load_settings

EDITABLE = ("DRAFT", "GENERATED")
PAID_OUT = ("APPROVED", "RELEASED")


class RunError(ValueError):
    pass


def program_ids(run: IncentiveRun) -> list[int]:
    try:
        return [int(i) for i in json.loads(run.program_ids or "[]")]
    except (ValueError, TypeError):
        return []


def snapshot(run: IncentiveRun) -> list[dict]:
    try:
        return json.loads(run.programs_snapshot or "[]")
    except ValueError:
        return []


class _FrozenProgram:
    """A program as frozen in a run (what compute_program needs)."""

    def __init__(self, data: dict):
        self.id = data["id"]
        self.name = data["name"]
        self.rule_type = data["rule_type"]
        self.applies_to = data["applies_to"]
        self.period_start = date.fromisoformat(data["period_start"])
        self.period_end = date.fromisoformat(data["period_end"])


def _freeze(program: IncentiveProgram) -> dict:
    return {
        "id": program.id,
        "name": program.name,
        "memo_no": program.memo_no,
        "rule_type": program.rule_type,
        "applies_to": program.applies_to,
        "period_start": program.period_start.isoformat(),
        "period_end": program.period_end.isoformat(),
        "settings": load_settings(program),
    }


def generate(db: Session, run: IncentiveRun, user_id: int | None) -> None:
    """(Re)computes the run's lines from its programs' current settings,
    freezing them into the run. Adjustment lines stay."""
    if run.status not in EDITABLE:
        raise RunError(f"This run is {run.status.lower()} and can't be generated again.")
    ids = program_ids(run)
    programs = db.query(IncentiveProgram).filter(IncentiveProgram.id.in_(ids or [0])).all()
    if not programs:
        raise RunError("Pick at least one incentive program.")

    frozen = [_freeze(p) for p in sorted(programs, key=lambda p: (p.period_start, p.id))]
    for line in [ln for ln in run.lines if not ln.is_adjustment]:
        run.lines.remove(line)
    db.flush()

    now = datetime.utcnow()
    for data in frozen:
        program = _FrozenProgram(data)
        if program.period_start > run.period_end or program.period_end < run.period_start:
            continue  # the program doesn't run in this period
        computed = compute_program(
            db, program, run.period_start, run.period_end, settings=data["settings"]
        )
        for row in computed["rows"]:
            if not row.get("employee_id") or not row["amount"]:
                continue
            details = {
                k: v
                for k, v in row.items()
                if k not in ("employee_id", "name", "department", "group", "amount")
            }
            run.lines.append(
                IncentiveRunLine(
                    employee_id=row["employee_id"],
                    employee_name=row["name"],
                    department=row.get("department"),
                    group=row.get("group"),
                    program_id=program.id,
                    program_name=program.name,
                    rule_type=program.rule_type,
                    amount=row["amount"],
                    details=json.dumps(details, default=str),
                    created_by=user_id,
                    created_at=now,
                )
            )
    run.programs_snapshot = json.dumps(frozen)
    run.status = "GENERATED"
    run.generated_at = now
    run.generated_by = user_id
    retotal(run)


def retotal(run: IncentiveRun) -> None:
    run.total = round(sum(float(line.amount or 0) for line in run.lines), 2)
    run.employee_count = len({line.employee_id for line in run.lines})


def serialize_line(line: IncentiveRunLine, with_details: bool = True) -> dict:
    data = {
        "id": line.id,
        "employee_id": line.employee_id,
        "employee_name": line.employee_name,
        "department": line.department,
        "group": line.group,
        "program_id": line.program_id,
        "program_name": line.program_name,
        "rule_type": line.rule_type,
        "rule_label": RULE_TYPES.get(line.rule_type, {}).get("label", "Adjustment"),
        "amount": float(line.amount or 0),
        "is_adjustment": line.is_adjustment,
        "note": line.note,
    }
    if with_details:
        try:
            data["details"] = json.loads(line.details) if line.details else None
        except ValueError:
            data["details"] = None
    return data


def payroll_totals(db: Session, start: date, end: date) -> dict:
    """{employee_id: {"total", "lines": [{run_id, run_name, program_name,
    amount, status}]}} -- approved / released "with payroll" runs whose
    payroll_date falls in start..end. Shown on the payroll as a separate
    line after net pay; never part of gross."""
    runs = (
        db.query(IncentiveRun)
        .filter(
            IncentiveRun.status.in_(PAID_OUT),
            IncentiveRun.release_method == "payroll",
            IncentiveRun.payroll_date >= start,
            IncentiveRun.payroll_date <= end,
        )
        .all()
    )
    result = {}
    for run in runs:
        for line in run.lines:
            entry = result.setdefault(str(line.employee_id), {"total": 0, "lines": []})
            entry["lines"].append({
                "run_id": run.id,
                "run_name": run.name,
                "program_name": line.program_name,
                "amount": float(line.amount or 0),
                "status": run.status,
            })
            entry["total"] = round(entry["total"] + float(line.amount or 0), 2)
    return result
