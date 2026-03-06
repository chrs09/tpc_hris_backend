from pydantic import BaseModel


class TripCreate(BaseModel):
    ticket_no: str
    driver_id: int


class LocationRequest(BaseModel):
    lat: float
    long: float
