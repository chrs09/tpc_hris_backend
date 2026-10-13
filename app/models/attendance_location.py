from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String

from app.core.database import Base


class AttendanceLocation(Base):
    """A place employees may time in/out from (selfie or kiosk), with its
    perimeter. Edited on HRIS -> Attendance Locations (module
    hris.attendance_locations). An employee assigned to locations
    (Employee.attendance_location_ids) is checked against those only;
    otherwise against every active one. Outside = accepted but flagged for
    the attendance approvers (see app/api/attendance.py)."""

    __tablename__ = "tpc_attendance_locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    radius_meters = Column(Integer, nullable=False, default=150)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
