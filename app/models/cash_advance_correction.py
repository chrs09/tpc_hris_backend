from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class CashAdvanceCorrection(Base):
    """A requested change to a cash advance (Finance -> CA Corrections),
    same idea as Trip Corrections: someone with Finance -> Cash Advance
    files it with a reason; an approver (admin / superadmin / Finance -> CA
    Corrections) approves or rejects. Only approval changes the balance.

    kind:
      adjustment -- what's owed changes by `change` (e.g. -300 when only
                    ₱700 of ₱1,000 was actually released)
      reversal   -- one deduction (`deduction_log_id`) is added back
                    because it was never taken from pay
    """

    __tablename__ = "tpc_cash_advance_corrections"

    id = Column(Integer, primary_key=True, index=True)
    cash_advance_request_id = Column(
        Integer, ForeignKey("tpc_cash_advance_requests.id"), nullable=False, index=True
    )
    kind = Column(String(20), nullable=False)  # adjustment | reversal
    # pending / approved / rejected / cancelled
    status = Column(String(20), nullable=False, default="pending", index=True)

    change = Column(Numeric(12, 2), nullable=True)  # adjustment
    deduction_log_id = Column(Integer, nullable=True)  # reversal
    # The reversed deduction's amount / cutoff when requested (for display).
    amount = Column(Numeric(12, 2), nullable=True)
    cutoff_period = Column(String(50), nullable=True)
    # Balance / amount owed when requested, for the reviewer.
    balance_before = Column(Numeric(12, 2), nullable=True)
    owed_before = Column(Numeric(12, 2), nullable=True)

    reason = Column(Text, nullable=False)

    requested_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    decided_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decision_note = Column(Text, nullable=True)
    # The ledger entry approval created.
    applied_log_id = Column(Integer, nullable=True)

    cash_advance_request = relationship("CashAdvanceRequest")
    requested_by = relationship("User", foreign_keys=[requested_by_user_id])
    decided_by = relationship("User", foreign_keys=[decided_by_user_id])
