"""System Logs (superadmin only): every change request with who sent it,
the URL, what was sent and the rows it changed. See
app/services/activity_log_service.py for how rows are written."""

import json
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_superadmin
from app.models.activity_log import ActivityLog
from app.models.user import User

router = APIRouter(prefix="/system-logs", tags=["System Logs"])

PH_OFFSET = timedelta(hours=8)


def _loads(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


@router.get("")
def list_system_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    # Matches URL, summary, username or the request body.
    search: str | None = Query(None),
    method: str | None = Query(None),
    username: str | None = Query(None),
    # "success" (2xx/3xx), "failed" (4xx/5xx) or empty for all.
    outcome: str | None = Query(None),
    # Only requests that changed data.
    changed_only: bool = Query(False),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    query = db.query(ActivityLog)
    if method:
        query = query.filter(ActivityLog.method == method.upper())
    if username and username.strip():
        query = query.filter(ActivityLog.username.ilike(f"%{username.strip()}%"))
    if outcome == "success":
        query = query.filter(ActivityLog.status_code < 400)
    elif outcome == "failed":
        query = query.filter(ActivityLog.status_code >= 400)
    if changed_only:
        query = query.filter(ActivityLog.changes.isnot(None))
    # Dates are Philippine days; rows are stored in UTC.
    if date_from:
        query = query.filter(ActivityLog.created_at >= datetime.combine(date_from, time.min) - PH_OFFSET)
    if date_to:
        query = query.filter(
            ActivityLog.created_at < datetime.combine(date_to + timedelta(days=1), time.min) - PH_OFFSET
        )
    if search and search.strip():
        like = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ActivityLog.path.ilike(like),
                ActivityLog.summary.ilike(like),
                ActivityLog.username.ilike(like),
                ActivityLog.body.ilike(like),
                ActivityLog.changes.ilike(like),
            )
        )

    total = query.count()
    rows = query.order_by(ActivityLog.id.desc()).offset(offset).limit(limit).all()

    impersonators = {
        u.id: u.username
        for u in db.query(User).filter(
            User.id.in_({r.impersonated_by for r in rows if r.impersonated_by} or {0})
        )
    }
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "created_at": r.created_at,
                "user_id": r.user_id,
                "username": r.username,
                "role": r.role,
                "impersonated_by": impersonators.get(r.impersonated_by) if r.impersonated_by else None,
                "method": r.method,
                "path": r.path,
                "query": r.query,
                "status_code": r.status_code,
                "duration_ms": r.duration_ms,
                "ip": r.ip,
                "user_agent": r.user_agent,
                "summary": r.summary,
                "body": _loads(r.body),
                "changes": _loads(r.changes) or [],
            }
            for r in rows
        ],
    }
