from fastapi import APIRouter, Depends, status
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
from app.models.user import User
from app.services.user_service import (
    create_user_service,
    update_user_service,
    get_user_revisions_service,
)

router = APIRouter(prefix="/users", tags=["Users"])


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
