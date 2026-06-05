from pydantic import BaseModel
from datetime import datetime, date
from typing import List, Optional


class AttendanceCreate(BaseModel):
    employee_id: int
    status: str
    attendance_date: date
    check_in_time: Optional[datetime] = None


class EmployeeAttendance(BaseModel):
    employee_id: int
    status: str


class AttendanceUpdate(BaseModel):
    employee_id: int
    attendance_date: date
    status: str


class BulkAttendanceMixed(BaseModel):
    attendances: List[EmployeeAttendance]


class AttendanceTimeAdjust(BaseModel): 
    check_in_time: str | None = None 
    check_out_time: str | None = None

class AttendanceResponse(BaseModel):
    id: int

    employee_id: int
    attendance_date: date

    # =========================
    # TIME IN
    # =========================
    check_in_time: Optional[datetime] = None

    time_in_latitude: Optional[float] = None
    time_in_longitude: Optional[float] = None
    time_in_address: Optional[str] = None

    # =========================
    # TIME OUT
    # =========================
    check_out_time: Optional[datetime] = None

    time_out_latitude: Optional[float] = None
    time_out_longitude: Optional[float] = None
    time_out_address: Optional[str] = None

    # =========================
    # PHOTO URLS
    # =========================
    time_in_photo_url: Optional[str] = None
    time_out_photo_url: Optional[str] = None

    # =========================
    # OTHER
    # =========================
    attendance_method: Optional[str] = None

    status: str

    created_by_user_id: int

    completed_trips: int = 0

    class Config:
        model_config = {"from_attributes": True}
