from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class CashAdvanceDeductionLog(Base):
    """One recorded deduction against a cash advance request -- e.g.
    "₱500 posted for the Sept 1-15 cutoff". The request's remaining
    balance is always amount - SUM(these entries), never a separately
    stored/mutable number, so it can't drift out of sync. Recorded
    manually by superadmin for now (not yet wired into automatic payslip
    generation)."""

    __tablename__ = "tpc_cash_advance_deduction_logs"

    id = Column(Integer, primary_key=True, index=True)

    cash_advance_request_id = Column(
        Integer, ForeignKey("tpc_cash_advance_requests.id"), nullable=False
    )

    amount = Column(Numeric(10, 2), nullable=False)
    note = Column(Text, nullable=True)

    recorded_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    cash_advance_request = relationship(
        "CashAdvanceRequest", back_populates="deduction_logs"
    )
    recorded_by = relationship("User", foreign_keys=[recorded_by_user_id])
