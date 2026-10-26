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
from app.utils.user_display import display_name

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
        # Employee's full name (username when there's no employee record)
        # -- shown in the sidebar greeting.
        "full_name": display_name(user),
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

    # By id, not username: usernames can be renamed in Users, and an old
    # token must neither break for the renamed user nor ever resolve to
    # someone who later takes the old username. Old tokens without a
    # user_id fall back to the username.
    user_id = payload.get("user_id")
    if user_id is not None:
        user = db.query(User).filter(User.id == user_id).first()
    else:
        user = (
            db.query(User)
            .filter(func.lower(User.username) == username.lower())
            .first()
        )

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


# =========================================================
# FORGOT PASSWORD -- "Forgot password?" on the login page emails a reset
# link (1 hour). The link is a token signed with a SEPARATE key (so it can
# never be used to log in) and tied to the current password hash, so it
# works once: after the password changes, the link is dead.
# =========================================================
_RESET_PURPOSE = "password_reset"
_RESET_MINUTES = 60
# Same address can't trigger another email within this window.
_RESET_COOLDOWN_S = 60
_last_reset_sent: dict[int, float] = {}


def _reset_key() -> str:
    return f"{settings.SECRET_KEY}:{_RESET_PURPOSE}"


def _password_fingerprint(user: User) -> str:
    import hashlib

    return hashlib.sha256((user.hashed_password or "").encode()).hexdigest()[:24]


def _user_email(user: User) -> str | None:
    employee = getattr(user, "employee", None)
    return user.email or (employee.email if employee else None)


@router.post("/forgot-password")
def forgot_password(
    identifier: str = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """Username or email -> email a reset link. Always the same reply, so
    it doesn't reveal which accounts exist."""
    import time

    from app.services.email_service import send_password_reset_email

    reply = {
        "message": (
            "If that account exists and has an email on file, a password reset "
            "link has been sent to it. The link expires in 1 hour."
        )
    }
    value = (identifier or "").strip().lower()
    if not value:
        raise HTTPException(status_code=400, detail="Enter your username or email.")

    user = (
        db.query(User)
        .filter(
            (func.lower(User.username) == value) | (func.lower(User.email) == value),
            User.is_active.is_(True),
        )
        .first()
    )
    if not user:
        from app.models.employees import Employee

        employee = (
            db.query(Employee).filter(func.lower(Employee.email) == value).first()
        )
        if employee:
            user = (
                db.query(User)
                .filter(User.employee_id == employee.id, User.is_active.is_(True))
                .first()
            )
    to_email = _user_email(user) if user else None
    if not user or not to_email:
        logger.info("Forgot password: no account/email for %r", value)
        return reply

    now = time.monotonic()
    if now - _last_reset_sent.get(user.id, -_RESET_COOLDOWN_S * 2) < _RESET_COOLDOWN_S:
        return reply
    _last_reset_sent[user.id] = now

    token = jwt.encode(
        {
            "sub": str(user.id),
            "purpose": _RESET_PURPOSE,
            "pfp": _password_fingerprint(user),
            "exp": datetime.utcnow() + timedelta(minutes=_RESET_MINUTES),
        },
        _reset_key(),
        algorithm=settings.ALGORITHM,
    )
    reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
    send_password_reset_email(
        to_email=to_email,
        name=display_name(user),
        username=user.username,
        reset_url=reset_url,
    )
    return reply


def _user_from_reset_token(db: Session, token: str) -> User:
    invalid = HTTPException(
        status_code=400,
        detail="This reset link is invalid or has expired. Request a new one.",
    )
    try:
        payload = jwt.decode(token, _reset_key(), algorithms=[settings.ALGORITHM])
    except JWTError:
        raise invalid
    if payload.get("purpose") != _RESET_PURPOSE:
        raise invalid
    user = db.query(User).filter(User.id == int(payload.get("sub") or 0)).first()
    if not user or not user.is_active or payload.get("pfp") != _password_fingerprint(user):
        # Unknown, deactivated, or the password already changed (used link).
        raise invalid
    return user


@router.get("/reset-password/check")
def check_reset_link(token: str, db: Session = Depends(get_db)):
    """For the reset form: is the link still good, and whose account."""
    user = _user_from_reset_token(db, token)
    return {"valid": True, "username": user.username}


@router.post("/reset-password")
def reset_password_with_link(
    token: str = Body(..., embed=True),
    new_password: str = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    user = _user_from_reset_token(db, token)
    if not new_password or len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    from app.models.user_revision import UserRevision

    user.hashed_password = hash_password(new_password)
    user.must_change_password = False
    db.add(
        UserRevision(
            user_id=user.id,
            field_changed="password",
            # Never the password itself -- only that it was reset, and how.
            old_value=None,
            new_value="reset (forgot password link)",
            reason=None,
            changed_by_user_id=user.id,
        )
    )
    db.commit()
    return {"message": "Your password has been changed. You can now log in.", "username": user.username}
