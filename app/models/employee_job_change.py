from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class EmployeeJobChange(Base):
    """Internal work history (201 -> Work History): the employee's
    department, position, pay type and rates from an effective date. Each
    row is the full set from that date on, so "what was true on day X"
    is the latest row on or before X. HIRED = the starting row (date
    hired). SCHEDULED rows are applied to the employee on their date
    (app/services/job_history.py); payroll pays each day by the row in
    effect that day, split across departments within a cutoff."""

    __tablename__ = "tpc_employee_job_changes"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        Integer, ForeignKey("tpc_employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    effective_date = Column(Date, nullable=False, index=True)
    kind = Column(String(20), nullable=False, default="CHANGE")  # HIRED / CHANGE
    status = Column(String(20), nullable=False, default="APPLIED")  # APPLIED / SCHEDULED / CANCELLED

    department = Column(String(100), nullable=True)
    position = Column(String(100), nullable=True)
    employment_type = Column(String(20), nullable=True)
    payroll_type = Column(String(20), nullable=True)
    daily_rate = Column(Numeric(10, 2), nullable=True)
    monthly_basic = Column(Numeric(10, 2), nullable=True)
    monthly_allow = Column(Numeric(10, 2), nullable=True)
    schedule_template_id = Column(Integer, ForeignKey("tpc_schedule_templates.id"), nullable=True)

    reason = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    applied_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    employee = relationship("Employee")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    schedule_template = relationship("ScheduleTemplate")
