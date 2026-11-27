"""Payroll -> Incentive Reports.

Every incentive program with a release date gets a report, made
automatically at 4:00 AM (PH) on that date: the program computed over its
period (e.g. trips from Nov 28, report on Nov 29). The job runs once at
4:00 AM; if it fails (no internet / database), it tries again every 30
minutes (4:30, 5:00 ...) until it works, then waits for the next 4:00 AM.
A server that was off at 4 AM tries at the next :00 / :30 after it starts.

Flow (Org Chart -> Payroll -> Incentive Reports):
  FOR_REVIEW  people with Incentive Reports (Can edit) approve, reject or
              edit each row; reject / edit need a reason.
  CONFIRMED   every row decided; someone ticked "Final confirm" (the trip
              coordinator) confirmed it -> it's with Finance.
  RELEASED    someone ticked "Release" (Finance) paid it out.
Finance can return a confirmed report to FOR_REVIEW with a note.

A program paid through a report can't also go in an Incentive Run, and a
program already in an approved / released Incentive Run gets no report.
"""

import json
import logging
import threading
import time as time_module
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.models.incentive_program import IncentiveProgram
from app.models.incentive_report import IncentiveReport, IncentiveReportLine
from app.services.incentives import compute_program, load_settings
from app.utils.timezone import utc_to_ph

logger = logging.getLogger(__name__)

GENERATE_AT = time(4, 0)  # PH
# Programs released before this day are left to Incentive Runs (no flood
# of reports for old programs when this goes live).
FIRST_RELEASE_DATE = date(2026, 11, 28)

VIEW_KEY = "payroll.incentive_reports"
CONFIRM_KEY = "payroll.incentive_reports_confirm"
RELEASE_KEY = "payroll.incentive_reports_release"


class ReportError(ValueError):
    pass


def ph_now() -> datetime:
    return utc_to_ph(datetime.utcnow())


def _log(report: IncentiveReport, user_id, action: str, note: str | None = None):
    entries = json.loads(report.log or "[]")
    entries.append({"at": datetime.utcnow().isoformat(), "by": user_id, "action": action, "note": note})
    report.log = json.dumps(entries)


def _in_paid_run(db: Session, program_id: int) -> bool:
    from app.models.incentive_run import IncentiveRun
    from app.services.incentive_runs import PAID_OUT, program_ids

    for run in db.query(IncentiveRun).filter(IncentiveRun.status.in_(PAID_OUT)).all():
        if program_id in program_ids(run):
            return True
    return False


def has_report(db: Session, program_id: int) -> bool:
    return (
        db.query(IncentiveReport.id).filter(IncentiveReport.program_id == program_id).first()
        is not None
    )


def _lines_for(program, computed: dict) -> list[dict]:
    """Report rows from a computed program. Daily Cash: one row per person
    per day (1st / 2nd / 3rd trip ...); other types: one per person."""
    out = []
    for row in computed["rows"]:
        if not row.get("employee_id"):
            continue
        base = {
            "employee_id": row["employee_id"],
            "employee_name": row.get("name") or "",
            "department": row.get("department"),
            "group": row.get("group"),
        }
        if program.rule_type == "daily_cash":
            for day in row.get("days") or []:
                if not day.get("amount"):
                    continue
                out.append({
                    **base,
                    "day": date.fromisoformat(day["date"]),
                    "amount": float(day["amount"]),
                    "details": {"trips": day.get("trips"), "trip_lines": day.get("trip_lines") or []},
                })
            continue
        if not row.get("amount"):
            continue
        out.append({
            **base,
            "day": None,
            "amount": float(row["amount"]),
            "details": {
                k: v for k, v in row.items()
                if k not in ("employee_id", "name", "department", "group", "amount")
            },
        })
    out.sort(key=lambda r: (r["day"] or date.min, r["employee_name"]))
    return out


def generate(db: Session, program: IncentiveProgram, user_id: int | None = None) -> IncentiveReport:
    """Makes the program's report (once). No commit."""
    if not program.release_date:
        raise ReportError("This program has no release date.")
    if has_report(db, program.id):
        raise ReportError("This program already has a report.")
    if _in_paid_run(db, program.id):
        raise ReportError("This program is already paid through an Incentive Run.")
    settings = load_settings(program)
    computed = compute_program(db, program, settings=settings)
    report = IncentiveReport(
        program_id=program.id,
        program_name=program.name,
        memo_no=program.memo_no,
        rule_type=program.rule_type,
        applies_to=program.applies_to,
        period_start=program.period_start,
        period_end=program.period_end,
        release_date=program.release_date,
        settings_snapshot=json.dumps(settings),
        status="FOR_REVIEW",
        generated_at=datetime.utcnow(),
        generated_by=user_id,
    )
    db.add(report)
    db.flush()
    total = 0.0
    for line in _lines_for(program, computed):
        total += line["amount"]
        db.add(IncentiveReportLine(
            report_id=report.id,
            employee_id=line["employee_id"],
            employee_name=line["employee_name"][:150],
            department=line["department"],
            group=line["group"],
            day=line["day"],
            computed_amount=line["amount"],
            amount=line["amount"],
            details=json.dumps(line["details"], default=str),
            status="pending",
        ))
    report.total = round(total, 2)
    _log(report, user_id, "generated", "Made by the 4 AM job" if user_id is None else "Made by hand")
    return report


def due_programs(db: Session, now_ph: datetime | None = None) -> list[IncentiveProgram]:
    """Active programs whose release date has come (from 4 AM PH) and
    that have no report yet."""
    now_ph = now_ph or ph_now()
    last_day = now_ph.date() if now_ph.time() >= GENERATE_AT else now_ph.date() - timedelta(days=1)
    programs = (
        db.query(IncentiveProgram)
        .filter(
            IncentiveProgram.is_active.is_(True),
            IncentiveProgram.release_date.isnot(None),
            IncentiveProgram.release_date >= FIRST_RELEASE_DATE,
            IncentiveProgram.release_date <= last_day,
        )
        .order_by(IncentiveProgram.release_date, IncentiveProgram.id)
        .all()
    )
    return [p for p in programs if not has_report(db, p.id) and not _in_paid_run(db, p.id)]


def generate_due(db: Session) -> tuple[int, int]:
    """-> (made, failed)."""
    made = failed = 0
    for program in due_programs(db):
        try:
            generate(db, program)
            db.commit()
            made += 1
        except Exception as exc:  # one bad program doesn't stop the rest
            db.rollback()
            failed += 1
            logger.warning("Incentive report for program %s not made: %s", program.id, exc)
    return made, failed


def recalc_total(report: IncentiveReport, lines) -> None:
    report.total = round(
        sum(float(ln.amount or 0) for ln in lines if ln.status != "rejected"), 2
    )


_started = False


def next_4am(now_ph: datetime) -> datetime:
    target = datetime.combine(now_ph.date(), GENERATE_AT)
    return target if now_ph < target else target + timedelta(days=1)


def next_half_hour(now_ph: datetime) -> datetime:
    base = now_ph.replace(second=0, microsecond=0)
    minutes = 30 - base.minute % 30
    return base + timedelta(minutes=minutes)


def run_once() -> bool:
    """One try. True = done (the database answered and every due report
    was made); False = try again in 30 minutes."""
    from app.core.database import SessionLocal

    db = None
    try:
        db = SessionLocal()
        made, failed = generate_due(db)
        if made:
            logger.info("Incentive reports made: %s", made)
        return failed == 0
    except Exception as exc:  # e.g. no connection
        logger.warning("Incentive reports not made, trying again in 30 min: %s", exc)
        return False
    finally:
        if db is not None:
            db.close()


def _has_missed() -> bool:
    """Reports that should already exist (server was off at 4 AM)."""
    from app.core.database import SessionLocal

    db = None
    try:
        db = SessionLocal()
        return bool(due_programs(db))
    except Exception:
        return True  # can't tell -- treat as a failed try
    finally:
        if db is not None:
            db.close()


def _sleep_until(when_ph: datetime) -> None:
    while True:
        left = (when_ph - ph_now()).total_seconds()
        if left <= 0:
            return
        time_module.sleep(min(left, 600))


def start_background_job() -> None:
    """Daemon thread: 4:00 AM PH once a day; on failure every 30 minutes
    (on the :00 / :30) until it works."""
    global _started
    if _started:
        return
    _started = True

    def retry_until_done():
        while not run_once():
            _sleep_until(next_half_hour(ph_now()))

    def loop():
        time_module.sleep(60)
        # Started after a 4 AM it missed: catch up on the next :00 / :30.
        if _has_missed():
            _sleep_until(next_half_hour(ph_now()))
            retry_until_done()
        while True:
            _sleep_until(next_4am(ph_now()))
            retry_until_done()

    threading.Thread(target=loop, name="incentive-reports", daemon=True).start()
