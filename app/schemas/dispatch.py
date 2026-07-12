from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# =====================================================
# Dispatch Helper
# =====================================================

class DispatchHelperBase(BaseModel):
    helper_id: int


class DispatchHelperCreate(DispatchHelperBase):
    pass


class DispatchHelperResponse(DispatchHelperBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =====================================================
# Dispatch Item
# =====================================================

class DispatchItemBase(BaseModel):
    shipment_no: str
    dealer_name: str
    hauler_name: Optional[str] = None

    driver_id: int
    vehicle_unit_id: int
    trip_rate_profile_id: int

    pallets: int = 0
    cases: int = 0


class DispatchItemCreate(DispatchItemBase):
    helpers: List[DispatchHelperCreate] = []


class DispatchItemUpdate(DispatchItemBase):
    helpers: List[DispatchHelperCreate] = []


class DispatchItemResponse(DispatchItemBase):
    id: int
    dispatch_id: int
    trip_id: Optional[int] = None

    status: str

    created_at: datetime
    updated_at: datetime

    helpers: List[DispatchHelperResponse] = []

    model_config = ConfigDict(from_attributes=True)


# =====================================================
# Dispatch
# =====================================================

class DispatchBase(BaseModel):
    plan_date: date


class DispatchCreate(DispatchBase):
    items: List[DispatchItemCreate]


class DispatchUpdate(DispatchBase):
    items: List[DispatchItemUpdate]


class DispatchResponse(DispatchBase):
    id: int

    status: str

    created_by: int

    created_at: datetime
    updated_at: datetime

    items: List[DispatchItemResponse] = []

    model_config = ConfigDict(from_attributes=True)