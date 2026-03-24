from pydantic import BaseModel
from datetime import datetime


class ReminderCreate(BaseModel):
    message: str


class ReminderResponse(BaseModel):
    id: int
    message: str
    created_by_user_id: int | None = None
    created_by_username: str | None = None
    is_resolved: bool
    created_at: datetime

    class Config:
        model_config = {"from_attributes": True}
