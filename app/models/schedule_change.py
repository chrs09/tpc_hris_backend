from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import relationship

from app.core.database import Base


class ScheduleChangeRequest(Base):
    """A different time in / out for ONE date, on top of the employee's
    regular work schedule (app/api/schedule_changes.py). Only employees
    with Employee.allow_schedule_change may file, and only before that
    day. The Org Chart heads with "Schedule Change" ticked approve in
    turn; once approved, that date's expected schedule (late, undertime,
    expected hours, overtime start, missed time in alert, payroll) is
    these times. The regular schedule itself never changes.

    time_in / time_out are PH wall-clock times.

    pending -> approved / rejected; cancelled by the employee while
    pending (or approved, before the day)."""

    __tablename__ = "tpc_schedule_changes"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=False, index=True)
    schedule_date = Column(Date, nullable=False, index=True)
    time_in = Column(Time, nullable=False)
    time_out = Column(Time, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)

    approval_chain = Column(Text, nullable=True)
    approval_step = Column(Integer, nullable=False, default=0, server_default="0")
    approval_log = Column(Text, nullable=True)

    filed_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    decided_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    employee = relationship("Employee")
