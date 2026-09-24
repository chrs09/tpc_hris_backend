from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.core.database import Base


class CashAdvancePurpose(Base):
    """A preset purpose/reason superadmin makes available for cash
    advance requests -- drivers pick from this list on mobile instead
    of typing a free-text reason. Mirrors
    CashAdvanceDeductionOption's shape exactly. The selected label is
    copied as plain text into CashAdvanceRequest.reason at filing time
    (no FK there), so deactivating/deleting a purpose here never
    changes historical requests."""

    __tablename__ = "tpc_cash_advance_purposes"

    id = Column(Integer, primary_key=True, index=True)

    label = Column(String(150), nullable=False)

    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
