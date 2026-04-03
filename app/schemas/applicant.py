from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


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

    onboarding_is_submitted: bool = False
    onboarding_submitted_at: Optional[datetime] = None

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


class ApplicantEducationPayload(BaseModel):
    level: Optional[str] = None
    institution: Optional[str] = None
    degree: Optional[str] = None
    year_from: Optional[str] = None
    year_to: Optional[str] = None
    skills: Optional[str] = None


class ApplicantEmploymentPayload(BaseModel):
    company_name: Optional[str] = None
    position: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class ApplicantReferencePayload(BaseModel):
    name: Optional[str] = None
    occupation: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None


class ApplicantOnboardingPayload(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    department: Optional[str] = None
    position: Optional[str] = None
    date_hired: Optional[date] = None

    birthday: Optional[date] = None
    birthplace: Optional[str] = None
    gender: Optional[str] = None
    civil_status: Optional[str] = None
    religion: Optional[str] = None
    citizenship: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    language: Optional[str] = None
    contact_number: Optional[str] = None
    current_address: Optional[str] = None
    provincial_address: Optional[str] = None

    spouse_name: Optional[str] = None
    father_name: Optional[str] = None
    mother_name: Optional[str] = None

    emergency_contact_name: Optional[str] = None
    emergency_contact_number: Optional[str] = None
    emergency_relationship: Optional[str] = None

    sss: Optional[str] = None
    philhealth: Optional[str] = None
    pagibig: Optional[str] = None
    tin: Optional[str] = None

    education_records: List[ApplicantEducationPayload] = []
    employment_history: List[ApplicantEmploymentPayload] = []
    references: List[ApplicantReferencePayload] = []

    class Config:
        from_attributes = True
