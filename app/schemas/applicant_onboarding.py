from datetime import date
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


def valid_school_year(value) -> Optional[str]:
    """A single 4-digit year, or empty. The employee record holds only
    10 characters, so "2013 2014 2018" would fail at convert."""
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    if not (text.isdigit() and len(text) == 4 and 1900 <= int(text) <= date.today().year + 10):
        raise ValueError("Pick one year (e.g. 2018). Use another row for each school.")
    return text


class ApplicantEducationPayload(BaseModel):
    level: Optional[str] = None
    institution: Optional[str] = None
    degree: Optional[str] = None
    year_from: Optional[str] = None
    year_to: Optional[str] = None
    skills: Optional[str] = None

    @field_validator("year_from", "year_to", mode="before")
    @classmethod
    def _one_year(cls, value):
        return valid_school_year(value)


class ApplicantEmploymentPayload(BaseModel):
    company_name: Optional[str] = None
    position: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    reason_for_leaving: Optional[str] = None
    salary_history: Optional[str] = None
    salary_type: Optional[str] = None


class ApplicantReferencePayload(BaseModel):
    name: Optional[str] = None
    position: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None


class ApplicantQuestionResponsePayload(BaseModel):
    question_key: str
    answer_text: Optional[str] = None


class ApplicantOnboardingPayload(BaseModel):
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    suffix: Optional[str] = None
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

    bank_type: Optional[str] = None
    account_name: Optional[str] = None
    account_number: Optional[str] = None

    education_records: List[ApplicantEducationPayload] = Field(default_factory=list)
    employment_history: List[ApplicantEmploymentPayload] = Field(default_factory=list)
    references: List[ApplicantReferencePayload] = Field(default_factory=list)
    question_responses: List[ApplicantQuestionResponsePayload] = Field(
        default_factory=list
    )
