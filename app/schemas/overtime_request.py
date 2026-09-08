from datetime import date, time, datetime

from pydantic import BaseModel


class OvertimeRequestCreate(BaseModel):
    requested_by_user_id: int
    ot_date: date
    time_in: time
    time_out: time
    reason: str


class OvertimeReviewAction(BaseModel):
    approved_hours: float | None = None
    remarks: str | None = None


class OvertimeApproverOption(BaseModel):
    id: int
    user_id: int
    username: str

    class Config:
        model_config = {"from_attributes": True}
