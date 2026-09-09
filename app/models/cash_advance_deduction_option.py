from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class CashAdvanceDeductionOption(Base):
    """A preset amount superadmin makes available for cash advance
    requests -- drivers pick from this list on mobile instead of typing
    an arbitrary amount, so payroll only ever deducts amounts the company
    has actually approved as options."""

    __tablename__ = "tpc_cash_advance_deduction_options"

    id = Column(Integer, primary_key=True, index=True)

    amount = Column(Numeric(10, 2), nullable=False)
    label = Column(String(100), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    requests = relationship(
        "CashAdvanceRequest", back_populates="deduction_option"
    )
