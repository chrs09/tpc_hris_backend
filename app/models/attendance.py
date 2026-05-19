from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Date,
    Float,
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime


class AttendanceRecord(Base):
    __tablename__ = "tpc_attendance_records"

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(
        Integer,
        ForeignKey("tpc_employees.id"),
        nullable=False,
    )

    attendance_date = Column(Date, nullable=False)

    check_in_time = Column(DateTime, nullable=True)

    time_in_latitude = Column(Float, nullable=True)
    time_in_longitude = Column(Float, nullable=True)
    time_in_address = Column(String(500), nullable=True)

    check_out_time = Column(DateTime, nullable=True)

    time_out_latitude = Column(Float, nullable=True)
    time_out_longitude = Column(Float, nullable=True)
    time_out_address = Column(String(500), nullable=True)

    status = Column(
        String(20),
        nullable=False,
        default="Present",
    )

    attendance_method = Column(String(30), nullable=True)

    created_by_user_id = Column(
        Integer,
        ForeignKey("tpc_users.id"),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    employee = relationship(
        "Employee",
        back_populates="attendance_records",
    )

    checked_in_by = relationship(
        "User",
        foreign_keys=[created_by_user_id],
        back_populates="attendance_created_records",
    )