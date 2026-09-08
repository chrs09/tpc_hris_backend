from pydantic import BaseModel
from datetime import date, datetime


class LeaveRequestCreate(BaseModel):
    start_date: date
    end_date: date
    reason: str


class LeaveReviewAction(BaseModel):
    remarks: str | None = None


class LeaveRequestResponse(BaseModel):
    id: int
    employee_id: int
    leave_type: str
    start_date: date
    end_date: date
    reason: str
    status: str
    review_remarks: str | None = None
    reviewed_by_user_id: int | None = None
    reviewed_at: datetime | None = None
    created_at: datetime

    class Config:
        model_config = {"from_attributes": True}
