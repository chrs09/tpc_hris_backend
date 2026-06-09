import logging
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException
from jose import JWTError, jwt
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User

# from app.models.employees import Employee
from app.schemas.user import UserLogin, UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])

logger = logging.getLogger("auth")


@router.get("/users", response_model=List[UserResponse])
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()


def get_access_expiry(role_value: str):
    if role_value in ["admin", "superadmin"]:
        return datetime.utcnow() + timedelta(hours=4)

    if role_value == "driver":
        return datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    return datetime.utcnow() + timedelta(hours=12)


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

    role_value = user.role.value if hasattr(user.role, "value") else user.role

    access_expires_at = get_access_expiry(role_value)

    refresh_expires_at = datetime.utcnow() + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )

    access_token = create_access_token(
        {
            "sub": user.username,
            "role": role_value,
            "user_id": user.id,
            "type": "access",
            "exp": access_expires_at,
        }
    )

    refresh_token = create_access_token(
        {
            "sub": user.username,
            "role": role_value,
            "user_id": user.id,
            "type": "refresh",
            "exp": refresh_expires_at,
        }
    )

    duration = access_expires_at - datetime.utcnow()

    logger.info(
        "LOGIN SUCCESS | user=%s | role=%s | access_expires=%s | refresh_expires=%s",
        user.username,
        role_value,
        access_expires_at,
        refresh_expires_at,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": role_value,
        "user_id": user.id,
        "employee_id": user.employee_id,
        "username": user.username,
        "must_change_password": user.must_change_password,
        "expires_at": access_expires_at.isoformat(),
        "expires_in_seconds": int(duration.total_seconds()),
        "refresh_expires_at": refresh_expires_at.isoformat(),
    }


@router.post("/refresh")
def refresh_access_token(
    refresh_token: str = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(
            refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )

        username = payload.get("sub")
        token_type = payload.get("type")

        if not username or token_type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")

    except JWTError:
        raise HTTPException(status_code=401, detail="Refresh token expired or invalid")

    user = db.query(User).filter(func.lower(User.username) == username.lower()).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    role_value = user.role.value if hasattr(user.role, "value") else user.role

    access_expires_at = get_access_expiry(role_value)

    new_access_token = create_access_token(
        {
            "sub": user.username,
            "role": role_value,
            "user_id": user.id,
            "type": "access",
            "exp": access_expires_at,
        }
    )

    duration = access_expires_at - datetime.utcnow()

    logger.info(
        "🔄 ACCESS TOKEN REFRESHED | user=%s | role=%s | expires=%s",
        user.username,
        role_value,
        access_expires_at,
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_at": access_expires_at.isoformat(),
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
