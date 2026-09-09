import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserRevisionResponse,
)
from app.core.dependencies import require_superadmin
from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.services.user_service import (
    create_user_service,
    update_user_service,
    get_user_revisions_service,
)

router = APIRouter(prefix="/users", tags=["Users"])

logger = logging.getLogger("auth")


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_superadmin),
):
    user, temp_password = create_user_service(data, db)

    return {
        "message": "User created successfully",
        "username": user.username,
        "temporary_password": temp_password,
    }


@router.get("/", response_model=List[UserResponse])
def get_users(
    db: Session = Depends(get_db),
    current_user=Depends(require_superadmin),
):
    users = db.query(User).all()
    return users


@router.patch("/{user_id}", status_code=status.HTTP_200_OK)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_superadmin),
):
    user = update_user_service(user_id, data, db, changed_by_user_id=current_user.id)

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
    current_user=Depends(require_superadmin),
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
