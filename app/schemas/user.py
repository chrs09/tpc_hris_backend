from datetime import datetime

from pydantic import BaseModel, EmailStr
from enum import Enum
from app.models.user import UserRole


class CreateUserRole(str, Enum):
    ADMIN = "admin"
    DRIVER = "driver"
    HELPER = "helper"
    EMPLOYEE = "employee"
    COORDINATOR = "coordinator"


class UpdateUserRole(str, Enum):
    # Includes SUPERADMIN so that PATCHing any *other* field (e.g.
    # is_active) on a superadmin account doesn't 422 just because the
    # frontend echoes back that account's current role in the payload.
    # update_user_service() still separately blocks ever changing a
    # superadmin account (role or status) -- this only fixes validation,
    # not the "cannot modify superadmin" business rule.
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    DRIVER = "driver"
    HELPER = "helper"
    EMPLOYEE = "employee"
    COORDINATOR_ADMIN = "coordinator_admin"
    COORDINATOR = "coordinator"
    PAYROLL_ADMIN = "payroll_admin"
    OFFICE_ADMIN = "office_admin"


class UserCreate(BaseModel):
    employee_id: int
    role: CreateUserRole


class UserUpdate(BaseModel):
    role: UpdateUserRole | None = None
    is_active: bool | None = None
    # Required by update_user_service() when is_active is being changed
    # from True to False -- becomes the UserRevision.reason for that change.
    reason: str | None = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr | None = None
    role: UserRole
    is_active: bool

    class Config:
        # orm_mode = True
        model_config = {"from_attributes": True}


class UserAssignableResponse(BaseModel):
    """A minimal, lower-sensitivity user shape (no email) for populating
    an assignee picker -- see GET /users/assignable. employee_name is the
    linked employee's full name, for display in place of the raw
    username (None if this account has no linked employee record)."""

    id: int
    username: str
    employee_name: str | None = None
    role: UserRole
    is_active: bool

    class Config:
        model_config = {"from_attributes": True}


class UserRevisionResponse(BaseModel):
    id: int
    field_changed: str
    old_value: str | None
    new_value: str | None
    reason: str | None
    changed_by_username: str | None
    created_at: datetime

    class Config:
        model_config = {"from_attributes": True}
