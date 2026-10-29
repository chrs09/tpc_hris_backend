from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class IncentiveRun(Base):
    """One payout batch of incentives, kept apart from payroll: some
    Incentive Policies programs computed for a period, with the programs'
    settings frozen at Generate (programs_snapshot) so a later rule change
    never alters it. Lines are the record of what each person earned.

    status: DRAFT -> GENERATED -> FOR_REVIEW -> APPROVED -> RELEASED
    (or CANCELLED). Regenerate until approved; released is final.
    release_method: "cash" (e.g. coordinator), "payroll" (shown on the
    payroll whose cutoff covers payroll_date, as a line after net pay --
    never in gross), or "bank".
    """

    __tablename__ = "tpc_incentive_runs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False)

    # [program ids] picked for the run; the frozen copy is set at Generate.
    program_ids = Column(Text, nullable=False, default="[]")
    programs_snapshot = Column(Text, nullable=True)

    release_method = Column(String(20), nullable=False, default="cash")
    payroll_date = Column(Date, nullable=True)

    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    notes = Column(Text, nullable=True)
    return_note = Column(String(500), nullable=True)

    total = Column(Numeric(14, 2), nullable=False, default=0)
    employee_count = Column(Integer, nullable=False, default=0)

    release_reference = Column(String(100), nullable=True)
    released_on = Column(Date, nullable=True)

    generated_at = Column(DateTime, nullable=True)
    generated_by = Column(Integer, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(Integer, nullable=True)
    released_at = Column(DateTime, nullable=True)
    released_by = Column(Integer, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(Integer, nullable=True)

    log = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    lines = relationship(
        "IncentiveRunLine",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="IncentiveRunLine.id",
    )


class IncentiveRunLine(Base):
    """What one person earned under one program in a run (or a manual
    adjustment, program_id null). Names are copied in, so the record reads
    the same even if the program or employee changes later."""

    __tablename__ = "tpc_incentive_run_lines"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer, ForeignKey("tpc_incentive_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id = Column(Integer, nullable=False, index=True)
    employee_name = Column(String(150), nullable=False)
    department = Column(String(100), nullable=True)
    group = Column("group_name", String(20), nullable=True)

    program_id = Column(Integer, nullable=True, index=True)
    program_name = Column(String(150), nullable=False)
    rule_type = Column(String(30), nullable=False)

    amount = Column(Numeric(12, 2), nullable=False, default=0)
    # The program's breakdown for this person (trips, tier, days, levels ...).
    details = Column(Text, nullable=True)

    is_adjustment = Column(Boolean, nullable=False, default=False)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    run = relationship("IncentiveRun", back_populates="lines")
