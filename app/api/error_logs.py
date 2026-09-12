from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_superadmin
from app.models.error_log import ErrorLog
from app.models.user import User

router = APIRouter(prefix="/error-logs", tags=["Error Logs"])


@router.get("")
def list_error_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_code: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Same events posted to Slack's #production-errors (see
    send_error_alert/send_response_alert in app/services/slack_service.py
    and the exception handlers in app/main.py), browsable here so a
    superadmin doesn't have to scroll Slack history."""
    query = db.query(ErrorLog)

    if status_code is not None:
        query = query.filter(ErrorLog.status_code == status_code)

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
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }
