from pydantic import BaseModel


class OvertimeReviewAction(BaseModel):
    approved_hours: float | None = None
    remarks: str | None = None
