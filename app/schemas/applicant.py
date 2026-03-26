from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


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
    is_converted_to_employee: bool
    employee_id: Optional[int] = None
    hired_at: Optional[datetime] = None
    converted_at: Optional[datetime] = None

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


class ConvertApplicantRequest(BaseModel):
    department: str
    position: Optional[str] = None


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
    is_converted_to_employee: bool
    employee_id: Optional[int] = None
    hired_at: Optional[datetime] = None
    converted_at: Optional[datetime] = None
    remarks: List[ApplicantRemarkResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True