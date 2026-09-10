from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User, UserRole
from app.core.config import settings

# from app.core.config import settings

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")

        if user_id is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive account",
        )

    return user


def get_current_admin(current_user: User = Depends(get_current_user)):
    """
    Ensures the current user has admin role.
    """

    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Admin privileges required.")

    return current_user


def get_current_trip_manager(current_user: User = Depends(get_current_user)):
    """
    Ensures the current user can manage trips/stores.

    Kept separate from get_current_admin so granting coordinators access
    to trip/store endpoints doesn't also widen their access to unrelated
    admin-only areas (payroll, user management, etc).
    """

    if current_user.role not in ["admin", "superadmin", "coordinator_admin"]:
        raise HTTPException(
            status_code=403, detail="Trip management privileges required."
        )

    return current_user


def require_superadmin(current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required",
        )
    return current_user


def require_role_or_module(roles: list[str], module_key: str):
    """Returns a FastAPI dependency that allows a request through if
    EITHER the caller's role is in `roles` (superadmin always allowed),
    OR the caller has been explicitly granted `module_key` on the
    Administrator -> Module Assignment page -- making a module grant a
    genuine override of role, not just a Sidebar nav cosmetic.

    A grant only counts once Employee.has_custom_module_access is True
    (i.e. an admin has actually configured this specific employee via
    Module Assignment -- see app/api/employee_module_access.py). Until
    then, role is the only thing that decides access, same as before
    this function existed.

    Use this in place of get_current_admin / get_current_trip_manager /
    an inline `if current_user.role not in [...]` check on any endpoint
    that backs a module listed in MODULE_GROUPS (both here and in
    tpc_hris_frontend/src/constants/modules.js -- module_key must match
    exactly, e.g. "hris.leave", "trip_management.stores")."""

    def _dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        role_value = (
            current_user.role.value
            if hasattr(current_user.role, "value")
            else current_user.role
        )

        if role_value == "superadmin" or role_value in roles:
            return current_user

        if current_user.employee_id:
            # Local imports to avoid a circular import at module load time
            # (employees/employee_module_access models import from
            # elsewhere in app.models, which can chain back here).
            from app.models.employees import Employee
            from app.models.employee_module_access import EmployeeModuleAccess

            employee = (
                db.query(Employee).filter(Employee.id == current_user.employee_id).first()
            )

            if employee and employee.has_custom_module_access:
                granted = (
                    db.query(EmployeeModuleAccess)
                    .filter(
                        EmployeeModuleAccess.employee_id == employee.id,
                        EmployeeModuleAccess.module_key == module_key,
                    )
                    .first()
                )
                if granted:
                    return current_user

        raise HTTPException(
            status_code=403,
            detail="You don't have access to this module.",
        )

    return _dependency