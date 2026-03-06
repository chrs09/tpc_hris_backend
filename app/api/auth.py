from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import UserLogin, UserResponse
from app.core.security import hash_password, verify_password, create_access_token
from datetime import datetime, timedelta

router = APIRouter(prefix="/auth", tags=["Auth"])


# router for getting list of user in tpc_user table
@router.get("/users", response_model=List[UserResponse])
def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return users


# endpoint for post login request
@router.post("/login")
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(func.lower(User.username) == credentials.username.lower())
        .first()
    )
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    token = create_access_token(
        {
            "sub": user.username,
            "role": user.role,
            "user_id": user.id,
            "exp": datetime.utcnow() + timedelta(minutes=60),
        }
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "user_id": user.id,
        "username": user.username,
        "must_change_password": user.must_change_password,
    }


# =============================
# CHANGE PASSWORD
# =============================
@router.post("/change-password")
def change_password(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    new_password = data.get("new_password")

    if not new_password or len(new_password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters"
        )

    current_user.hashed_password = hash_password(new_password)
    current_user.must_change_password = False

    db.commit()

    return {"message": "Password updated successfully"}
