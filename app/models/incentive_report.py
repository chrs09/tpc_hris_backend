from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text

from app.core.database import Base


class IncentiveReport(Base):
    """Payroll -> Incentive Reports: one per incentive program, made
    automatically at 4 AM (PH) on the program's release date (see
    app/services/incentive_reports.py).

    FOR_REVIEW -- people with Incentive Reports approve, reject or edit
                  each row (with a reason).
    CONFIRMED  -- every row decided and the trip coordinator (Org Chart:
                  Incentive Reports -> Final confirm) confirmed it; now
                  with Finance.
    RELEASED   -- Finance paid it out (Incentive Reports -> Release).
    Finance can return a confirmed report to FOR_REVIEW with a note.
    """

    __tablename__ = "tpc_incentive_reports"

    id = Column(Integer, primary_key=True, index=True)
    program_id = Column(
        Integer, ForeignKey("tpc_incentive_programs.id"), nullable=False, unique=True, index=True
    )
    program_name = Column(String(150), nullable=False)
    memo_no = Column(String(30), nullable=True)
    rule_type = Column(String(30), nullable=False)
    applies_to = Column(String(50), nullable=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    release_date = Column(Date, nullable=False, index=True)
    # The program's settings as they were when the report was made.
    settings_snapshot = Column(Text, nullable=True)

    status = Column(String(20), nullable=False, default="FOR_REVIEW", index=True)
    total = Column(Numeric(14, 2), nullable=False, default=0)
    return_note = Column(String(500), nullable=True)

    generated_at = Column(DateTime, nullable=True)
    generated_by = Column(Integer, nullable=True)  # None = the 4 AM job
    confirmed_at = Column(DateTime, nullable=True)
    confirmed_by = Column(Integer, nullable=True)
    released_at = Column(DateTime, nullable=True)
    released_by = Column(Integer, nullable=True)
    release_method = Column(String(20), nullable=True)  # cash | bank
    release_reference = Column(String(100), nullable=True)

    # JSON list of {at, by, action, note}.
    log = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class IncentiveReportLine(Base):
    """One row: a person (Daily Cash: a person on one day)."""

    __tablename__ = "tpc_incentive_report_lines"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(
        Integer, ForeignKey("tpc_incentive_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id = Column(Integer, nullable=False, index=True)
    employee_name = Column(String(150), nullable=False)
    department = Column(String(100), nullable=True)
    group = Column("group_name", String(20), nullable=True)
    day = Column(Date, nullable=True)  # Daily Cash rows

    # What the rules gave, and what will be paid.
    computed_amount = Column(Numeric(12, 2), nullable=False, default=0)
    amount = Column(Numeric(12, 2), nullable=False, default=0)
    # JSON: the trips / counts behind the amount.
    details = Column(Text, nullable=True)

    status = Column(String(20), nullable=False, default="pending")  # pending | approved | rejected
    reason = Column(String(500), nullable=True)
    decided_by = Column(Integer, nullable=True)
    decided_at = Column(DateTime, nullable=True)
