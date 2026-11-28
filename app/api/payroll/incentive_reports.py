"""Payroll -> Incentive Reports. See app/services/incentive_reports.py."""

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import has_editable_grant, require_role_or_module
from app.models.incentive_program import IncentiveProgram
from app.models.incentive_report import IncentiveReport, IncentiveReportLine
from app.models.user import User
from app.services import incentive_reports as R
from app.utils.timezone import utc_to_ph
from app.utils.user_display import display_name

router = APIRouter(prefix="/incentive-reports", tags=["Incentive Reports"])

_require_view = require_role_or_module(
    roles=[], module_key=[R.VIEW_KEY, R.CONFIRM_KEY, R.RELEASE_KEY]
)


def _can(db: Session, user: User) -> dict:
    return {
        "approve": has_editable_grant(db, user, [R.VIEW_KEY]),
        "confirm": has_editable_grant(db, user, [R.CONFIRM_KEY]),
        "release": has_editable_grant(db, user, [R.RELEASE_KEY]),
    }


def _need(db: Session, user: User, key: str, what: str):
    if not has_editable_grant(db, user, [key]):
        raise HTTPException(
            status_code=403,
            detail=f"You need Payroll → Incentive Reports → {what} on the Org Chart.",
        )


def _fmt(dt):
    return utc_to_ph(dt).strftime("%b %d, %Y %I:%M %p") if dt else None


def _names(db: Session, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: display_name(u) for u in db.query(User).filter(User.id.in_(ids)).all()}


def _report_or_404(db: Session, report_id: int) -> IncentiveReport:
    report = db.query(IncentiveReport).filter(IncentiveReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


def _lines(db: Session, report_id: int):
    return (
        db.query(IncentiveReportLine)
        .filter(IncentiveReportLine.report_id == report_id)
        .order_by(IncentiveReportLine.day, IncentiveReportLine.employee_name, IncentiveReportLine.id)
        .all()
    )


def _summary(report: IncentiveReport, lines, names: dict) -> dict:
    counts = {"pending": 0, "approved": 0, "rejected": 0}
    for ln in lines:
        counts[ln.status] = counts.get(ln.status, 0) + 1
    return {
        "id": report.id,
        "program_id": report.program_id,
        "program_name": report.program_name,
        "memo_no": report.memo_no,
        "rule_type": report.rule_type,
        "applies_to": report.applies_to,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "release_date": report.release_date.isoformat(),
        "status": report.status,
        "total": float(report.total or 0),
        "rows": len(lines),
        "counts": counts,
        "return_note": report.return_note,
        "generated_at": _fmt(report.generated_at),
        "generated_by": names.get(report.generated_by) if report.generated_by else "Automatic (4 AM)",
        "confirmed_at": _fmt(report.confirmed_at),
        "confirmed_by": names.get(report.confirmed_by),
        "released_at": _fmt(report.released_at),
        "released_by": names.get(report.released_by),
        "release_method": report.release_method,
        "release_reference": report.release_reference,
    }


@router.get("")
def list_reports(db: Session = Depends(get_db), current_user: User = Depends(_require_view)):
    reports = db.query(IncentiveReport).order_by(
        IncentiveReport.release_date.desc(), IncentiveReport.id.desc()
    ).all()
    all_lines = {}
    if reports:
        for ln in db.query(IncentiveReportLine).filter(
            IncentiveReportLine.report_id.in_([r.id for r in reports])
        ):
            all_lines.setdefault(ln.report_id, []).append(ln)
    names = _names(
        db,
        [r.generated_by for r in reports] + [r.confirmed_by for r in reports] + [r.released_by for r in reports],
    )
    # Programs whose release date has passed with no report yet (made by
    # hand from here if the 4 AM job hasn't run).
    today = R.ph_now().date()
    waiting = [
        {"id": p.id, "name": p.name, "release_date": p.release_date.isoformat(), "rule_type": p.rule_type}
        for p in db.query(IncentiveProgram)
        .filter(
            IncentiveProgram.is_active.is_(True),
            IncentiveProgram.release_date.isnot(None),
            IncentiveProgram.release_date <= today,
            IncentiveProgram.release_date >= R.FIRST_RELEASE_DATE,
        )
        .order_by(IncentiveProgram.release_date.desc())
        .all()
        if not R.has_report(db, p.id)
    ]
    upcoming = [
        {"id": p.id, "name": p.name, "release_date": p.release_date.isoformat(), "rule_type": p.rule_type}
        for p in db.query(IncentiveProgram)
        .filter(
            IncentiveProgram.is_active.is_(True),
            IncentiveProgram.release_date > today,
        )
        .order_by(IncentiveProgram.release_date)
        .limit(10)
        .all()
    ]
    return {
        "reports": [_summary(r, all_lines.get(r.id, []), names) for r in reports],
        "waiting": waiting,
        "upcoming": upcoming,
        "can": _can(db, current_user),
    }


@router.get("/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db), current_user: User = Depends(_require_view)):
    report = _report_or_404(db, report_id)
    lines = _lines(db, report.id)
    names = _names(
        db,
        [report.generated_by, report.confirmed_by, report.released_by] + [ln.decided_by for ln in lines],
    )
    log = json.loads(report.log or "[]")
    log_names = _names(db, [e.get("by") for e in log])
    return {
        **_summary(report, lines, names),
        "lines": [
            {
                "id": ln.id,
                "employee_id": ln.employee_id,
                "employee_name": ln.employee_name,
                "department": ln.department,
                "group": ln.group,
                "day": ln.day.isoformat() if ln.day else None,
                "computed_amount": float(ln.computed_amount or 0),
                "amount": float(ln.amount or 0),
                "details": json.loads(ln.details or "{}"),
                "status": ln.status,
                "edited": ln.status == "approved" and float(ln.amount or 0) != float(ln.computed_amount or 0),
                "reason": ln.reason,
                "decided_by": names.get(ln.decided_by),
                "decided_at": _fmt(ln.decided_at),
            }
            for ln in lines
        ],
        "log": [
            {
                "at": _fmt(datetime.fromisoformat(e["at"])) if e.get("at") else None,
                "by": log_names.get(e.get("by")) or ("Automatic" if e.get("by") is None else None),
                "action": e.get("action"),
                "note": e.get("note"),
            }
            for e in log
        ],
        "can": _can(db, current_user),
    }


class LineDecision(BaseModel):
    action: str  # approve | reject | edit | undo
    amount: float | None = None
    reason: str | None = None


@router.put("/lines/{line_id}")
def decide_line(
    line_id: int,
    payload: LineDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    _need(db, current_user, R.VIEW_KEY, "Approve rows (Can edit)")
    line = db.query(IncentiveReportLine).filter(IncentiveReportLine.id == line_id).first()
    if not line:
        raise HTTPException(status_code=404, detail="Row not found.")
    report = _report_or_404(db, line.report_id)
    if report.status != "FOR_REVIEW":
        raise HTTPException(status_code=400, detail="This report is no longer in review.")
    reason = (payload.reason or "").strip()[:500] or None

    if payload.action == "approve":
        line.status, line.amount, line.reason = "approved", line.computed_amount, None
    elif payload.action == "reject":
        if not reason:
            raise HTTPException(status_code=400, detail="Give a reason for rejecting this row.")
        line.status, line.amount, line.reason = "rejected", 0, reason
    elif payload.action == "edit":
        if payload.amount is None or payload.amount < 0:
            raise HTTPException(status_code=400, detail="Enter the amount to pay (0 or more).")
        if not reason:
            raise HTTPException(status_code=400, detail="Give a reason for changing the amount.")
        line.status, line.amount, line.reason = "approved", round(payload.amount, 2), reason
    elif payload.action == "undo":
        line.status, line.amount, line.reason = "pending", line.computed_amount, None
    else:
        raise HTTPException(status_code=400, detail="Unknown action.")
    line.decided_by = None if payload.action == "undo" else current_user.id
    line.decided_at = None if payload.action == "undo" else datetime.utcnow()
    R.recalc_total(report, _lines(db, report.id))
    db.commit()
    return {"message": "Saved.", "total": float(report.total or 0)}


@router.post("/{report_id}/approve-pending")
def approve_pending(report_id: int, db: Session = Depends(get_db), current_user: User = Depends(_require_view)):
    _need(db, current_user, R.VIEW_KEY, "Approve rows (Can edit)")
    report = _report_or_404(db, report_id)
    if report.status != "FOR_REVIEW":
        raise HTTPException(status_code=400, detail="This report is no longer in review.")
    lines = _lines(db, report.id)
    now = datetime.utcnow()
    count = 0
    for ln in lines:
        if ln.status == "pending":
            ln.status, ln.amount, ln.reason = "approved", ln.computed_amount, None
            ln.decided_by, ln.decided_at = current_user.id, now
            count += 1
    R.recalc_total(report, lines)
    db.commit()
    return {"message": f"{count} row(s) approved.", "total": float(report.total or 0)}


@router.post("/{report_id}/confirm")
def confirm_report(report_id: int, db: Session = Depends(get_db), current_user: User = Depends(_require_view)):
    _need(db, current_user, R.CONFIRM_KEY, "Final confirm")
    report = _report_or_404(db, report_id)
    if report.status != "FOR_REVIEW":
        raise HTTPException(status_code=400, detail="Only a report in review can be confirmed.")
    lines = _lines(db, report.id)
    pending = sum(1 for ln in lines if ln.status == "pending")
    if pending:
        raise HTTPException(status_code=400, detail=f"{pending} row(s) still need approving or rejecting.")
    R.recalc_total(report, lines)
    report.status = "CONFIRMED"
    report.confirmed_at, report.confirmed_by = datetime.utcnow(), current_user.id
    report.return_note = None
    R._log(report, current_user.id, "confirmed", "Passed to Finance")
    db.commit()
    return {"message": "Confirmed. The report is now with Finance."}


class ReturnBody(BaseModel):
    note: str


@router.post("/{report_id}/return")
def return_report(
    report_id: int, payload: ReturnBody, db: Session = Depends(get_db), current_user: User = Depends(_require_view)
):
    if not (has_editable_grant(db, current_user, [R.RELEASE_KEY]) or has_editable_grant(db, current_user, [R.CONFIRM_KEY])):
        raise HTTPException(status_code=403, detail="You need Final confirm or Release to return a report.")
    report = _report_or_404(db, report_id)
    if report.status != "CONFIRMED":
        raise HTTPException(status_code=400, detail="Only a confirmed report can be returned.")
    note = (payload.note or "").strip()[:500]
    if not note:
        raise HTTPException(status_code=400, detail="Say what needs fixing.")
    report.status = "FOR_REVIEW"
    report.return_note = note
    report.confirmed_at = report.confirmed_by = None
    R._log(report, current_user.id, "returned", note)
    db.commit()
    return {"message": "Returned for review."}


class ReleaseBody(BaseModel):
    method: str = "cash"  # cash | bank
    reference: str | None = None


@router.post("/{report_id}/release")
def release_report(
    report_id: int, payload: ReleaseBody, db: Session = Depends(get_db), current_user: User = Depends(_require_view)
):
    _need(db, current_user, R.RELEASE_KEY, "Release")
    report = _report_or_404(db, report_id)
    if report.status != "CONFIRMED":
        raise HTTPException(status_code=400, detail="Only a confirmed report can be released.")
    if payload.method not in ("cash", "bank"):
        raise HTTPException(status_code=400, detail="Pick cash or bank.")
    report.status = "RELEASED"
    report.release_method = payload.method
    report.release_reference = (payload.reference or "").strip()[:100] or None
    report.released_at, report.released_by = datetime.utcnow(), current_user.id
    R._log(report, current_user.id, "released", f"{payload.method}{' · ' + report.release_reference if report.release_reference else ''}")
    db.commit()
    return {"message": "Released."}


@router.get("/programs/{program_id}/preview")
def preview_program(program_id: int, db: Session = Depends(get_db), current_user: User = Depends(_require_view)):
    """Before generating / regenerating: the rows the report would have
    and every trip in the period (counted or not, with the reason)."""
    program = db.query(IncentiveProgram).filter(IncentiveProgram.id == program_id).first()
    if not program:
        raise HTTPException(status_code=404, detail="Program not found.")
    data = R.preview(db, program)
    for ln in data["lines"]:
        ln["details"] = json.loads(json.dumps(ln["details"], default=str))
    return data


@router.post("/programs/{program_id}/generate")
def generate_now(program_id: int, db: Session = Depends(get_db), current_user: User = Depends(_require_view)):
    """Make a program's report now (its release date has come)."""
    _need(db, current_user, R.VIEW_KEY, "Approve rows (Can edit)")
    program = db.query(IncentiveProgram).filter(IncentiveProgram.id == program_id).first()
    if not program:
        raise HTTPException(status_code=404, detail="Program not found.")
    if not program.release_date or program.release_date > R.ph_now().date():
        raise HTTPException(status_code=400, detail="The report is made on the program's release date.")
    try:
        report = R.generate(db, program, current_user.id)
    except R.ReportError as error:
        raise HTTPException(status_code=400, detail=str(error))
    db.commit()
    return {"message": "Report made.", "id": report.id}


@router.post("/{report_id}/regenerate")
def regenerate(report_id: int, db: Session = Depends(get_db), current_user: User = Depends(_require_view)):
    """Make the report again from the trips as they are now (e.g. after a
    trip was corrected). Only while no row has been decided."""
    _need(db, current_user, R.VIEW_KEY, "Approve rows (Can edit)")
    report = _report_or_404(db, report_id)
    if report.status != "FOR_REVIEW":
        raise HTTPException(status_code=400, detail="Only a report in review can be made again.")
    lines = _lines(db, report.id)
    if any(ln.status != "pending" for ln in lines):
        raise HTTPException(
            status_code=400, detail="Some rows are already decided. Undo them first to make the report again."
        )
    program = db.query(IncentiveProgram).filter(IncentiveProgram.id == report.program_id).first()
    if not program:
        raise HTTPException(status_code=404, detail="The program was deleted.")
    old_log = report.log
    for ln in lines:
        db.delete(ln)
    db.delete(report)
    db.flush()
    try:
        new = R.generate(db, program, current_user.id)
    except R.ReportError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error))
    new.log = old_log
    R._log(new, current_user.id, "regenerated", None)
    db.commit()
    return {"message": "Report made again.", "id": new.id}
