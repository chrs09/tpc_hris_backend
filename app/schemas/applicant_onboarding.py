from datetime import date
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


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


class ApplicantQuestionResponsePayload(BaseModel):
    question_key: str
    answer_text: Optional[str] = None


class ApplicantOnboardingPayload(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    department: Optional[str] = None
    position: Optional[str] = None

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

    current_salary: Optional[str] = None
    expected_salary: Optional[str] = None
    salary_type: Optional[str] = None

    sss: Optional[str] = None
    philhealth: Optional[str] = None
    pagibig: Optional[str] = None
    tin: Optional[str] = None

    education_records: List[ApplicantEducationPayload] = Field(default_factory=list)
    employment_history: List[ApplicantEmploymentPayload] = Field(default_factory=list)
    references: List[ApplicantReferencePayload] = Field(default_factory=list)
    question_responses: List[ApplicantQuestionResponsePayload] = Field(
        default_factory=list
    )
