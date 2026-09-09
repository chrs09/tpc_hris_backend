from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class EmployeeModuleAccess(Base):
    """Per-employee grant for a single sidebar submodule (e.g.
    "hris.attendance", "trip_management.stores"). Replaces hardcoded
    role-based sidebar gating for the assignable groups (HRIS, Payroll,
    Trip Management, Finance) with an explicit per-employee checklist
    managed on the Module Assignment page. One row per granted submodule;
    absence of a row means no access."""

    __tablename__ = "tpc_employee_module_access"

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(
        Integer, ForeignKey("tpc_employees.id", ondelete="CASCADE"), nullable=False
    )

    module_key = Column(String(80), nullable=False)

    granted_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    employee = relationship("Employee", foreign_keys=[employee_id])
    granted_by = relationship("User", foreign_keys=[granted_by_user_id])

    __table_args__ = (
        UniqueConstraint("employee_id", "module_key", name="uq_employee_module"),
    )
