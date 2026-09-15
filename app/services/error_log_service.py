"""Persists the same error events posted to Slack (see
send_error_alert/send_response_alert in app/services/slack_service.py)
into tpc_error_logs, so a superadmin can browse them in the app itself.
Kept as its own DB session (not a request-scoped `db: Session = Depends(...)`)
because this is called from exception handlers in app/main.py, which
FastAPI does not inject dependencies into.
"""

import logging

from fastapi import Request
from jose import JWTError, jwt

from app.core.database import SessionLocal
from app.core.dependencies import SECRET_KEY, ALGORITHM
from app.models.error_log import ErrorLog
from app.models.user import User

logger = logging.getLogger("error_log")


def get_request_user(request: Request) -> tuple[int | None, str | None]:
    """Best-effort "who sent this request" for error reporting -- decodes
    the same Bearer token get_current_user() would, but never raises: an
    expired/missing/garbage token (or none at all, e.g. a request that
    never got that far) just means the error gets logged as
    unauthenticated instead of blocking the error response itself."""
    auth_header = request.headers.get("Authorization") or request.headers.get(
        "authorization"
    )
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None, None

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None, None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
    except JWTError:
        return None, None

    if user_id is None:
        return None, None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        return (user.id, user.username) if user else (user_id, None)
    except Exception:
        logger.exception("Failed to resolve request user for error log")
        return user_id, None
    finally:
        db.close()


def log_error(
    method: str,
    url: str,
    status_code: int,
    detail=None,
    error_type: str | None = None,
    traceback_text: str | None = None,
    user_id: int | None = None,
    username: str | None = None,
) -> None:
    """Writes one row to tpc_error_logs. Never raises -- a failure here
    must never turn into a second error on top of the one being handled,
    same contract as send_slack_alert."""
    db = SessionLocal()
    try:
        db.add(
            ErrorLog(
                method=method,
                url=url[:2048],
                status_code=status_code,
                error_type=error_type,
                detail=str(detail)[:5000] if detail is not None else None,
                traceback=traceback_text[-5000:] if traceback_text else None,
                user_id=user_id,
                username=username,
            )
        )
        db.commit()
    except Exception:
        logger.exception("Failed to write error log to database")
        db.rollback()
    finally:
        db.close()
