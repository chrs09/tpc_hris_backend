from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.error_log import ErrorLog
from app.models.user import User

router = APIRouter(prefix="/error-logs", tags=["Error Logs"])

_require_error_logs_access = require_role_or_module(
    roles=[], module_key="administrator.error_logs"
)


@router.get("")
def list_error_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_code: int | None = Query(None),
    # Matches URL, error type, message or username (contains, any case).
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_error_logs_access),
):
    """Same events posted to Slack's #production-errors (see
    send_error_alert/send_response_alert in app/services/slack_service.py
    and the exception handlers in app/main.py), browsable here so a
    superadmin doesn't have to scroll Slack history."""
    query = db.query(ErrorLog)

    if status_code is not None:
        query = query.filter(ErrorLog.status_code == status_code)

    if search and search.strip():
        like = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ErrorLog.url.ilike(like),
                ErrorLog.error_type.ilike(like),
                ErrorLog.detail.ilike(like),
                ErrorLog.username.ilike(like),
                ErrorLog.method.ilike(like),
            )
        )

    total = query.count()

    rows = (
        query.order_by(ErrorLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "items": [
            {
                "id": row.id,
                "method": row.method,
                "url": row.url,
                "status_code": row.status_code,
                "error_type": row.error_type,
                "detail": row.detail,
                "traceback": row.traceback,
                "user_id": row.user_id,
                "username": row.username,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }
