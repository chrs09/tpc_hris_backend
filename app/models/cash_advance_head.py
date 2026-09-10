from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class CashAdvanceHead(Base):
    """Reporting hierarchy, specifically for cash advance approvals: which
    user is the "cash advance immediate head" of a given employee
    department. Deliberately a SEPARATE table from DepartmentHead (the
    general/overtime immediate head) rather than a second row there --
    DepartmentHead.department has a hard one-row-per-department unique
    constraint, and a department may want a different person approving
    cash advances than the one approving overtime. One row per
    department; every employee in that department shares the same cash
    advance head. See file_cash_advance_request() in
    app/api/cash_advance_request.py for how this is resolved at filing
    time (falls back to a superadmin if no entry exists yet for the
    department, instead of blocking the request)."""

    __tablename__ = "tpc_cash_advance_heads"

    id = Column(Integer, primary_key=True, index=True)

    department = Column(String(50), nullable=False, unique=True, index=True)

    head_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)

    updated_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    head_user = relationship("User", foreign_keys=[head_user_id])
    updated_by = relationship("User", foreign_keys=[updated_by_user_id])
