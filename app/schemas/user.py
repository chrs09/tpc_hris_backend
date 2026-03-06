from pydantic import BaseModel, EmailStr
from enum import Enum
from app.models.user import UserRole


class CreateUserRole(str, Enum):
    ADMIN = "admin"
    DRIVER = "driver"
    HELPER = "helper"
    EMPLOYEE = "employee"


class UpdateUserRole(str, Enum):
    ADMIN = "admin"
    DRIVER = "driver"
    HELPER = "helper"
    EMPLOYEE = "employee"


class UserCreate(BaseModel):
    employee_id: int
    role: CreateUserRole


class UserUpdate(BaseModel):
    role: UpdateUserRole | None = None
    is_active: bool | None = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: UserRole
    is_active: bool

    class Config:
        # orm_mode = True
        model_config = {"from_attributes": True}
