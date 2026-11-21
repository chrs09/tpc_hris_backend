from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT

from app.core.database import Base


class PayrollRun(Base):
    """The status of one department's payroll for one cutoff:

        DRAFT -> GENERATED -> FOR_REVIEW -> CONTRIBUTIONS -> HEAD_REVIEW
              -> APPROVED -> LOCKED -> PAID

    CONTRIBUTIONS: someone with Payroll -> Government Contributions edits
    SSS / PhilHealth / Pag-IBIG / tax only, then sends it to the head
    (HEAD_REVIEW), who approves.

    Generating can be repeated until APPROVED (the per-employee rows in
    payroll_deductions are upserted, never duplicated). Once LOCKED, the
    period's attendance / OT / adjustments / trips can no longer change
    (app/services/payroll_lock.py)."""

    __tablename__ = "tpc_payroll_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    department = Column(String(50), nullable=False, index=True)
    # Same key as payroll_deductions.cutoff_period, e.g. "2026-10-01_2026-10-15"
    cutoff_period = Column(String(50), nullable=False, index=True)
    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)

    status = Column(String(20), nullable=False, default="DRAFT")
    # Payday, set on New Pay Run (prefilled from the group's cutoff rule;
    # never a Sunday -- moved to the Saturday before). Null on older runs:
    # the page falls back to the rule's payday.
    pay_date = Column(Date, nullable=True)

    employee_count = Column(Integer, nullable=False, default=0)
    total_gross = Column(Numeric(14, 2), nullable=False, default=0)
    total_net = Column(Numeric(14, 2), nullable=False, default=0)

    generated_at = Column(DateTime, nullable=True)
    generated_by = Column(Integer, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, nullable=True)
    # For Review -> Contributions (forwarded) and Contributions -> Head
    # Review (government contributions done).
    # Deductions step (at Generated): confirmed before Submit for Review;
    # Generate again or a deductions change clears it.
    deductions_confirmed_at = Column(DateTime, nullable=True)
    deductions_confirmed_by = Column(Integer, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(Integer, nullable=True)
    contributions_at = Column(DateTime, nullable=True)
    contributions_by = Column(Integer, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(Integer, nullable=True)
    locked_at = Column(DateTime, nullable=True)
    locked_by = Column(Integer, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    paid_by = Column(Integer, nullable=True)

    # Pay run snapshot: every employee's computed payroll row (with the
    # day-by-day breakdown) as of Generate, JSON. The pay run page shows
    # this instead of recalculating, so figures don't move afterwards;
    # only Generate again (Draft / Generated) replaces it.
    snapshot = Column(Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=True)
    snapshot_at = Column(DateTime, nullable=True)
    snapshot_by = Column(Integer, nullable=True)
    # Pre-check at Generate, JSON: {"items": [{key, label, count}], "note",
    # "by", "at"} -- what was still open and who generated anyway.
    precheck = Column(Text, nullable=True)

    # Latest "returned for correction" / "unlocked" reason.
    return_note = Column(String(500), nullable=True)
    # JSON list of {"action", "status", "by", "at", "note"}.
    log = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("department", "cutoff_period", name="uq_payroll_run_dept_cutoff"),
    )
