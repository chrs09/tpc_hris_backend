from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class CashAdvanceTerms(Base):
    """Cash advance terms & conditions text, editable by superadmin. Only
    ever expected to have a single row (id=1) -- always fetch/update "the
    current terms" rather than tracking a list. A driver must acknowledge
    this exact text (see CashAdvanceRequest.terms_accepted) when filing a
    request.

    Also carries `max_pay_periods`, the global cap on how many pay
    periods a cash advance is allowed to stretch across. A request is
    only accepted if ceil(amount / deduction_per_pay_amount) is within
    this cap -- the driver must pick a per-pay preset large enough to
    fit, rather than the system silently recalculating a non-preset
    deduction amount to force compliance.

    `max_loan_amount` is a separate, simpler cap: the largest total
    amount a single cash advance request may ask for. Null means no
    cap."""

    __tablename__ = "tpc_cash_advance_terms"

    id = Column(Integer, primary_key=True, index=True)

    content = Column(Text, nullable=False)

    max_pay_periods = Column(Integer, nullable=False, default=6)
    max_loan_amount = Column(Numeric(10, 2), nullable=True)

    updated_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    updated_by = relationship("User", foreign_keys=[updated_by_user_id])
