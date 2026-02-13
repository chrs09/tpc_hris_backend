from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional


class AttendanceCreate(BaseModel):
    employee_id: int
    status: str
    check_in_time: Optional[datetime] = None  # defaults to now if not provided


class EmployeeAttendance(BaseModel):
    employee_id: int
    status: str


class BulkAttendanceMixed(BaseModel):
    attendances: List[EmployeeAttendance]  # plural to match endpoint


class AttendanceResponse(BaseModel):
    id: int
    employee_id: int
    check_in_time: datetime
    status: str
    created_by_user_id: int

    class Config:
        model_config = {"from_attributes": True}  # Pydantic v2