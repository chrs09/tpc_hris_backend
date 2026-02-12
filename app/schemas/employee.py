from typing import Optional
from pydantic import BaseModel, EmailStr
from datetime import date

class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    position: str
    date_hired: date
    department: str
    # created_by_user_id: int

class EmployeeUpdate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    position: str
    date_hired: date
    department: str
    # created_by_user_id: int


class EmployeeResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: EmailStr
    position: str
    date_hired: date
    department: str
    # created_by_user_id: Optional[int]  # Make this optional in case it's not always returned
    # created_by_user_id: int

    class Config:
        # orm_mode = True
        model_config = {
            "from_attributes": True
        }