from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func

from app.core.database import Base


class PayrollRun(Base):
    """The status of one department's payroll for one cutoff:

        DRAFT -> GENERATED -> FOR_REVIEW -> APPROVED -> LOCKED -> PAID

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

    employee_count = Column(Integer, nullable=False, default=0)
    total_gross = Column(Numeric(14, 2), nullable=False, default=0)
    total_net = Column(Numeric(14, 2), nullable=False, default=0)

    generated_at = Column(DateTime, nullable=True)
    generated_by = Column(Integer, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(Integer, nullable=True)
    locked_at = Column(DateTime, nullable=True)
    locked_by = Column(Integer, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    paid_by = Column(Integer, nullable=True)

    # Latest "returned for correction" / "unlocked" reason.
    return_note = Column(String(500), nullable=True)
    # JSON list of {"action", "status", "by", "at", "note"}.
    log = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("department", "cutoff_period", name="uq_payroll_run_dept_cutoff"),
    )
