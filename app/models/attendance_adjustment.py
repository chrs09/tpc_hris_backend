from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class AttendanceAdjustment(Base):
    """Audit trail for attendance edited by hand (table/grid view): what
    changed, from what to what, who did it, when and why. Nothing is
    overwritten without a trace -- the first entry's old value is the
    original. field: "created", "check_in_time", "check_out_time",
    "status" or "remarks"; times are stored as PH "YYYY-MM-DD HH:MM AM"."""

    __tablename__ = "tpc_attendance_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    attendance_id = Column(
        Integer,
        ForeignKey("tpc_attendance_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field = Column(String(30), nullable=False)
    old_value = Column(String(255), nullable=True)
    new_value = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True)
    changed_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    changed_by = relationship("User", foreign_keys=[changed_by_user_id])
