from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class DriverInfo(BaseModel):
    id: int
    username: Optional[str]
    last_name: Optional[str]

    class Config:
        orm_mode = True


class AdminTripResponse(BaseModel):
    id: int
    ticket_no: str
    status: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    driver: DriverInfo
    stops_count: int

    class Config:
        # orm_mode = True
        model_config = {"from_attributes": True}
