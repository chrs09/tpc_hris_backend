from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class MobilePageAccess(Base):
    """Per-employee grant for a single mobile-app page (e.g.
    "ot_approvals", "trip_monitor"). Mirrors EmployeeModuleAccess's shape
    exactly but is a separate table/flag (Employee.has_custom_mobile_access)
    -- kept independent from the web's module-assignment system so the two
    never interfere with each other. One row per granted page; absence of
    a row means no access. See app/api/mobile_page_access.py."""

    __tablename__ = "tpc_mobile_page_access"

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(
        Integer, ForeignKey("tpc_employees.id", ondelete="CASCADE"), nullable=False
    )

    page_key = Column(String(50), nullable=False)

    granted_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    employee = relationship("Employee", foreign_keys=[employee_id])
    granted_by = relationship("User", foreign_keys=[granted_by_user_id])

    __table_args__ = (
        UniqueConstraint("employee_id", "page_key", name="uq_employee_mobile_page"),
    )
