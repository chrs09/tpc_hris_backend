from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class AttendanceAlert(Base):
    """A scheduled employee with no time in -- asked of their immediate
    head (see app/services/attendance_alerts.py). One per employee per day.

    Same day (after the wait time): the head picks Late (the day becomes
    Delay once they time in), 2nd half (Halfday) or Absent (with a reason).
    A past day still without attendance: "Does this employee work on this
    day?" -- No = Absent (reason), Yes = the employee files a time
    correction (TimeCorrectionRequest); its approval closes this.

    status: open (waiting on the head), waiting_time_in (Late / 2nd half
    picked), waiting_employee (Yes -- waiting on their time correction),
    closed. decision: late, second_half, absent, works, timed_in,
    corrected."""

    __tablename__ = "tpc_attendance_alerts"
    __table_args__ = (
        UniqueConstraint("employee_id", "attendance_date", name="uq_attendance_alert_day"),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=False, index=True)
    attendance_date = Column(Date, nullable=False, index=True)
    # Their time in that day per their schedule.
    scheduled_in = Column(Time, nullable=True)
    # Who answers it (NULL = no head on the Org Chart: superadmins).
    head_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True, index=True)

    status = Column(String(20), nullable=False, default="open", index=True)
    decision = Column(String(20), nullable=True)
    reason = Column(Text, nullable=True)
    decided_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)

    # Emails sent: to the head (new alert) / to the employee (head said Yes).
    head_emailed_at = Column(DateTime, nullable=True)
    employee_emailed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)

    employee = relationship("Employee")
    head = relationship("User", foreign_keys=[head_user_id])
    decided_by = relationship("User", foreign_keys=[decided_by_user_id])
