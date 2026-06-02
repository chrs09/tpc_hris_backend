from pydantic import BaseModel, EmailStr
from datetime import date


class EmployeeCreate(BaseModel):
    first_name: str
    middle_name: str
    suffix: str
    last_name: str
    email: EmailStr
    position: str
    date_hired: date
    department: str
    schedule_template_id: int | None = None
    # created_by_user_id: int


class EmployeeUpdate(BaseModel):
    first_name: str
    middle_name: str
    suffix: str
    last_name: str
    email: EmailStr
    position: str
    date_hired: date
    department: str
    schedule_template_id: int | None = None
    # created_by_user_id: int


class EmployeeResponse(BaseModel):
    id: int
    first_name: str
    middle_name: str
    suffix: str
    last_name: str
    email: EmailStr
    position: str
    date_hired: date
    department: str
    is_active: bool
    daily_rate: float | None = None
    employment_type: str | None = None
    payroll_type: str | None = None
    schedule_template_id: int | None = None
    # created_by_user_id: Optional[int]  # Make this optional in case it's not always returned
    # created_by_user_id: int

    class Config:
        # orm_mode = True
        model_config = {"from_attributes": True}
