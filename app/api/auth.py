import logging
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserLogin, UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])

logger = logging.getLogger("auth")


@router.get("/users", response_model=List[UserResponse])
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()


@router.post("/login")
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(func.lower(User.username) == credentials.username.lower())
        .first()
    )

    if not user or not verify_password(credentials.password, user.hashed_password):
        logger.warning("❌ Failed login attempt for username: %s", credentials.username)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        logger.warning("⛔ Inactive user tried to login: %s", user.username)
        raise HTTPException(status_code=403, detail="Account is inactive")

    # ✅ FIX ENUM VALUE
    role_value = user.role.value if hasattr(user.role, "value") else user.role

    # ✅ ROLE-BASED EXPIRY
    if role_value in ["admin", "superadmin"]:
        expires_at = datetime.utcnow() + timedelta(hours=4)
    elif role_value == "driver":
        expires_at = datetime.utcnow() + timedelta(hours=36)
        # expires_at = datetime.utcnow() + timedelta(minutes=1)
    else:
        expires_at = datetime.utcnow() + timedelta(hours=12)

    token = create_access_token(
        {
            "sub": user.username,
            "role": role_value,
            "user_id": user.id,
            "exp": expires_at,
        }
    )

    duration = expires_at - datetime.utcnow()

    # ✅ CLEAN LOG (WITH HOURS)
    hours = duration.total_seconds() / 3600

    logger.info(
        "LOGIN SUCCESS | user=%s | role=%s | duration_hours=%.2f | expires_at=%s",
        user.username,
        role_value,
        hours,
        expires_at,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": role_value,
        "user_id": user.id,
        "username": user.username,
        "must_change_password": user.must_change_password,
        "expires_at": expires_at.isoformat(),
        "expires_in_seconds": int(duration.total_seconds()),
    }


@router.post("/change-password")
def change_password(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_password = data.get("new_password")

    if not new_password or len(new_password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters",
        )

    current_user.hashed_password = hash_password(new_password)
    current_user.must_change_password = False

    db.commit()

    logger.info("🔑 Password updated for user: %s", current_user.username)

    return {"message": "Password updated successfully"}
