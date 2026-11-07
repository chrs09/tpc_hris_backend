from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class TimeCorrectionRequest(Base):
    """An employee asks to set / fix their time in and/or time out for a
    day (forgot to time in or out, or a wrong time), with a reason. It goes
    to the Org Chart attendance approvers (like Leave / Overtime); the last
    approval writes the times into the attendance record, each change in
    the attendance audit log (AttendanceAdjustment). Times are naive UTC
    like AttendanceRecord; None = that side isn't being changed."""

    __tablename__ = "tpc_time_corrections"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=False, index=True)
    attendance_date = Column(Date, nullable=False, index=True)

    time_in = Column(DateTime, nullable=True)
    time_out = Column(DateTime, nullable=True)
    reason = Column(Text, nullable=False)
    # Proof (optional): photos / screenshots for the time in and time out.
    time_in_photo_url = Column(String(1000), nullable=True)
    time_out_photo_url = Column(String(1000), nullable=True)

    # pending / approved / rejected / cancelled
    status = Column(String(20), nullable=False, default="pending", index=True)

    approval_chain = Column(Text, nullable=True)
    approval_step = Column(Integer, nullable=False, default=0, server_default="0")
    approval_log = Column(Text, nullable=True)

    filed_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    decided_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    employee = relationship("Employee")
    filed_by = relationship("User", foreign_keys=[filed_by_user_id])
    decided_by = relationship("User", foreign_keys=[decided_by_user_id])
