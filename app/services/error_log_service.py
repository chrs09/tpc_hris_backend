"""Persists the same error events posted to Slack (see
send_error_alert/send_response_alert in app/services/slack_service.py)
into tpc_error_logs, so a superadmin can browse them in the app itself.
Kept as its own DB session (not a request-scoped `db: Session = Depends(...)`)
because this is called from exception handlers in app/main.py, which
FastAPI does not inject dependencies into.
"""

import logging

from app.core.database import SessionLocal
from app.models.error_log import ErrorLog

logger = logging.getLogger("error_log")


def log_error(
    method: str,
    url: str,
    status_code: int,
    detail=None,
    error_type: str | None = None,
    traceback_text: str | None = None,
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
            )
        )
        db.commit()
    except Exception:
        logger.exception("Failed to write error log to database")
        db.rollback()
    finally:
        db.close()
