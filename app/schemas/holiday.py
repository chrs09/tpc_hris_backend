from datetime import date, datetime
from typing import Optional, Literal
from pydantic import BaseModel, ConfigDict

HolidayType = Literal["regular", "special_non_working", "special_working"]
Scope = Literal["national", "local"]


class HolidayBase(BaseModel):
    holiday_name: str
    holiday_date: date
    holiday_type: HolidayType
    scope: Scope
    province: Optional[str] = None
    city: Optional[str] = None
    remarks: Optional[str] = None
    is_active: bool = True


class HolidayCreate(HolidayBase):
    override_api: bool = False  # set True if this should replace an API holiday on the same date


class HolidayUpdate(BaseModel):
    holiday_name: Optional[str] = None
    holiday_date: Optional[date] = None
    holiday_type: Optional[HolidayType] = None
    scope: Optional[Scope] = None
    province: Optional[str] = None
    city: Optional[str] = None
    remarks: Optional[str] = None
    is_active: Optional[bool] = None
    override_api: Optional[bool] = None


class HolidayResponse(HolidayBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: Literal["api", "manual"]
    override_api: bool
    created_at: datetime
    updated_at: datetime