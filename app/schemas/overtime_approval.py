from pydantic import BaseModel
from datetime import date, datetime


class OvertimeApprovalCreate(BaseModel):
    employee_id: int

    cutoff_start: date
    cutoff_end: date

    detected_ot_hours: float
    approved_ot_hours: float

    remarks: str | None = None


class OvertimeApprovalResponse(BaseModel):
    id: int

    employee_id: int

    cutoff_start: date
    cutoff_end: date

    detected_ot_hours: float
    approved_ot_hours: float

    status: str

    remarks: str | None

    approved_by_user_id: int | None
    approved_at: datetime | None

class OvertimeApprovalRequest(BaseModel):
    employee_id: int
    cutoff_start: date
    cutoff_end: date
    approved_ot_hours: float
    remarks: str | None = None

    class Config:
        from_attributes = True

