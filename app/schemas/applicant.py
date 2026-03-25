from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class ApplicantResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    contact_number: str
    position_applied: str
    status: str
    created_at: datetime
    cv_url: Optional[str] = None

    class Config:
        from_attributes = True


class ApplicantStatusUpdate(BaseModel):
    status: str


class ApplicantRemarkCreate(BaseModel):
    remark: str
    status: Optional[str] = None


class ApplicantRemarkResponse(BaseModel):
    id: int
    applicant_id: int
    status: Optional[str] = None
    remark: str
    created_by_user_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ApplicantDetailResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    contact_number: str
    position_applied: str
    status: str
    created_at: datetime
    cv_url: Optional[str] = None
    remarks: List[ApplicantRemarkResponse] = []

    class Config:
        from_attributes = True