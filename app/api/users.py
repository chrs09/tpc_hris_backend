import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserAssignableResponse,
    UserRevisionResponse,
)
from app.core.dependencies import get_current_user, require_superadmin, require_role_or_module
from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.services.user_service import (
    create_user_service,
    bulk_create_users_service,
    update_user_service,
    get_user_revisions_service,
)

router = APIRouter(prefix="/users", tags=["Users"])

logger = logging.getLogger("auth")

# Users list/create/edit can be delegated via Module Assignment
# (administrator.users). Impersonation stays superadmin-only regardless --
# it hands out a live session as another account, which is a step beyond
# what a module grant should cover.
_require_users_access = require_role_or_module(roles=[], module_key="administrator.users")


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user=Depends(_require_users_access),
):
    user, temp_password = create_user_service(data, db)

    return {
        "message": "User created successfully",
        "username": user.username,
        "temporary_password": temp_password,
    }


@router.post("/bulk-create")
def bulk_create_users(
    db: Session = Depends(get_db),
    current_user=Depends(_require_users_access),
):
    """Creates a login account (role=employee, same username/password
    convention as a single manual create) for every active employee who
    doesn't already have one. Returns the full credential list once --
    same as the single-create flow, nothing is emailed/stored anywhere
    else, so the admin needs to copy/print this response before leaving
    the page."""
    return bulk_create_users_service(db)


@router.get("/", response_model=List[UserResponse])
def get_users(
    db: Session = Depends(get_db),
    current_user=Depends(_require_users_access),
):
    users = db.query(User).options(joinedload(User.employee)).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "employee_name": (
                f"{u.employee.first_name} {u.employee.last_name}"
                if u.employee
                else None
            ),
        }
        for u in users
    ]


@router.get("/assignable", response_model=List[UserAssignableResponse])
def get_assignable_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A minimal, lower-sensitivity user listing (id/username/role/active,
    no email) for populating an assignee picker -- e.g. Tickets'
    "Assign to" select or Hierarchy's immediate-head select. Open to any
    authenticated user, unlike GET /users/ which requires full Users
    management access (administrator.users) -- someone granted only
    administrator.tickets or administrator.hierarchy still needs a user
    list to actually use those pages, and this exposes far less than the
    full endpoint."""
    users = (
        db.query(User)
        .options(joinedload(User.employee))
        .filter(User.is_active.is_(True))
        .all()
    )
    return [
        {
            "id": u.id,
            "username": u.username,
            "employee_name": (
                f"{u.employee.first_name} {u.employee.last_name}"
                if u.employee
                else None
            ),
            "role": u.role,
            "is_active": u.is_active,
        }
        for u in users
    ]


@router.patch("/{user_id}", status_code=status.HTTP_200_OK)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(_require_users_access),
):
    caller_role = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else current_user.role
    )
    user = update_user_service(
        user_id,
        data,
        db,
        changed_by_user_id=current_user.id,
        caller_is_superadmin=(caller_role == "superadmin"),
    )

    return {
        "message": "User updated successfully",
        "id": user.id,
        "role": user.role,
    }


@router.post("/{user_id}/impersonate")
def impersonate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Issues a short-lived access token for another user's account, so
    superadmin can see exactly what that person sees (Sidebar, module
    access, dashboards) without knowing their password. The frontend
    keeps the superadmin's own token stashed separately so "Return to
    Superadmin" can restore it without a fresh login."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    if target.id == current_user.id:
        raise HTTPException(
            status_code=400, detail="You're already logged in as yourself."
        )

    if target.role == UserRole.SUPERADMIN:
        raise HTTPException(
            status_code=400, detail="Cannot impersonate another superadmin account."
        )

    if not target.is_active:
        raise HTTPException(
            status_code=400, detail="Cannot impersonate an inactive account."
        )

    role_value = target.role.value if hasattr(target.role, "value") else target.role
    access_expires_at = datetime.utcnow() + timedelta(hours=1)

    access_token = create_access_token(
        {
            "sub": target.username,
            "role": role_value,
            "user_id": target.id,
            "type": "access",
            "exp": access_expires_at,
            "impersonated_by": current_user.id,
        }
    )

    logger.warning(
        "IMPERSONATION START | superadmin=%s (id=%s) -> target=%s (id=%s, role=%s)",
        current_user.username,
        current_user.id,
        target.username,
        target.id,
        role_value,
    )

    duration = access_expires_at - datetime.utcnow()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": role_value,
        "user_id": target.id,
        "employee_id": target.employee_id,
        "username": target.username,
        # Never force the superadmin through this account's own
        # must-change-password flow -- they're just viewing, not taking
        # over the account permanently.
        "must_change_password": False,
        "expires_at": access_expires_at.isoformat(),
        "expires_in_seconds": int(duration.total_seconds()),
    }


@router.get("/{user_id}/revisions", response_model=List[UserRevisionResponse])
def get_user_revisions(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(_require_users_access),
):
    revisions = get_user_revisions_service(user_id, db)

    return [
        {
            "id": revision.id,
            "field_changed": revision.field_changed,
            "old_value": revision.old_value,
            "new_value": revision.new_value,
            "reason": revision.reason,
            "changed_by_username": (
                revision.changed_by_user.username
                if revision.changed_by_user
                else None
            ),
            "created_at": revision.created_at,
        }
        for revision in revisions
    ]
