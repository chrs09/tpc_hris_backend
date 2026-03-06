from fastapi import APIRouter, Depends, status
from typing import List
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.core.dependencies import require_superadmin
from app.models.user import User
from app.services.user_service import create_user_service, update_user_service

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
    user = update_user_service(user_id, data, db)

    return {
        "message": "User updated successfully",
        "id": user.id,
        "role": user.role,
    }
