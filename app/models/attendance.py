from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Date
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime


class AttendanceRecord(Base):
    __tablename__ = "tpc_attendance_records"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=False)
    attendance_date = Column(Date, nullable=False)
    check_in_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    status = Column(String(20), nullable=False)  # e.g., 'Present', 'Absent', 'On Leave'
    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)

    employee = relationship("Employee", back_populates="attendance_records")
    checked_in_by = relationship(
        "User",
        foreign_keys=[created_by_user_id],
        back_populates="attendance_created_records",
    )
