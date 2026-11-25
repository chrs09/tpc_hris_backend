"""System Logs: records every change request and the rows it changed.

How it works
- The middleware in app/main.py calls `start_capture()` before a POST /
  PUT / PATCH / DELETE runs and `finish()` after the response.
- While a request runs, a SQLAlchemy `after_flush` hook collects every row
  that was created, updated (old -> new per column) or deleted, into a
  list kept in a context variable for that request.
- `finish()` writes one ActivityLog row in its own session. It never
  raises: a logging failure must not break the request.
"""

import contextvars
import datetime as dt
import decimal
import json
import logging
import re
from datetime import datetime, timedelta

from jose import JWTError, jwt
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.dependencies import ALGORITHM, SECRET_KEY
from app.models.activity_log import ActivityLog
from app.models.user import User

logger = logging.getLogger("activity_log")

LOGGED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# High-frequency or non-change calls left out (GPS pings every few seconds).
SKIP_PATH_PATTERNS = [
    re.compile(r"/track(-location)?/?$"),
    re.compile(r"/auth/refresh"),
]

# Tables whose changes aren't worth listing (the logs themselves, GPS).
SKIP_TABLES = {"tpc_activity_logs", "tpc_error_logs", "tpc_gps_logs"}

SECRET_KEY_RE = re.compile(
    r"(password|passwd|token|secret|otp|api_key|authorization|hashed|signature)", re.I
)

MAX_BODY = 6000
MAX_CHANGES = 150
MAX_VALUE = 300
RETENTION_DAYS = 180

_changes: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "activity_changes", default=None
)


# ------------------------------------------------------------------ helpers
def _plain(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if hasattr(value, "value"):  # enums
        return value.value
    text = str(value)
    return text if len(text) <= MAX_VALUE else text[:MAX_VALUE] + "…"


def redact(data):
    """Hide secrets anywhere in a JSON body."""
    if isinstance(data, dict):
        return {
            k: ("•••" if SECRET_KEY_RE.search(str(k)) else redact(v)) for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact(v) for v in data[:200]]
    return data


def _pk(obj):
    try:
        ident = inspect(obj).identity
        if ident:
            return ident[0] if len(ident) == 1 else list(ident)
    except Exception:
        pass
    return getattr(obj, "id", None)


def _columns(obj):
    mapper = inspect(obj).mapper
    return [attr for attr in mapper.column_attrs]


def _record_flush(session, flush_context):
    changes = _changes.get()
    if changes is None or len(changes) >= MAX_CHANGES:
        return
    try:
        for obj in list(session.new):
            table = getattr(obj, "__tablename__", None)
            if not table or table in SKIP_TABLES:
                continue
            fields = {}
            for attr in _columns(obj):
                value = getattr(obj, attr.key, None)
                if value is None:
                    continue
                fields[attr.key] = [None, "•••" if SECRET_KEY_RE.search(attr.key) else _plain(value)]
            changes.append({"action": "created", "table": table, "id": _pk(obj), "fields": fields})

        for obj in list(session.dirty):
            table = getattr(obj, "__tablename__", None)
            if not table or table in SKIP_TABLES:
                continue
            state = inspect(obj)
            fields = {}
            for attr in _columns(obj):
                hist = state.attrs[attr.key].history
                if not hist.has_changes():
                    continue
                old = hist.deleted[0] if hist.deleted else None
                new = hist.added[0] if hist.added else None
                if old == new:
                    continue
                if SECRET_KEY_RE.search(attr.key):
                    fields[attr.key] = ["•••", "•••"]
                else:
                    fields[attr.key] = [_plain(old), _plain(new)]
            if fields:
                changes.append({"action": "updated", "table": table, "id": _pk(obj), "fields": fields})

        for obj in list(session.deleted):
            table = getattr(obj, "__tablename__", None)
            if not table or table in SKIP_TABLES:
                continue
            changes.append({"action": "deleted", "table": table, "id": _pk(obj), "fields": {}})
        del changes[MAX_CHANGES:]
    except Exception:
        logger.exception("System Logs: couldn't read flushed changes")


event.listen(Session, "after_flush", _record_flush)


def _who(headers) -> tuple:
    auth = headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None, None, None, None
    try:
        payload = jwt.decode(auth.split(" ", 1)[1].strip(), SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None, None, None, None
    return (
        payload.get("user_id"),
        payload.get("sub"),
        payload.get("role"),
        payload.get("impersonated_by"),
    )


def _label(table: str) -> str:
    return table.removeprefix("tpc_").replace("_", " ").rstrip("s") if table else "record"


def summarize(changes: list, status_code: int) -> str:
    if status_code >= 400:
        return f"Refused ({status_code})" if status_code < 500 else f"Failed ({status_code})"
    if not changes:
        return "No data changed"
    first = changes[0]
    text = f"{first['action'].capitalize()} {_label(first['table'])}"
    if first.get("id") is not None:
        text += f" #{first['id']}"
    if first["action"] == "updated" and first["fields"]:
        text += " (" + ", ".join(list(first["fields"])[:4]) + ")"
    if len(changes) > 1:
        text += f" + {len(changes) - 1} more"
    return text[:255]


# ---------------------------------------------------------------- lifecycle
def should_log(method: str, path: str) -> bool:
    if method.upper() not in LOGGED_METHODS:
        return False
    return not any(p.search(path) for p in SKIP_PATH_PATTERNS)


def start_capture():
    """Begin collecting this request's changes. Returns (token, list);
    the middleware resets the token itself (same context) and passes the
    list to finish(), which runs in a worker thread."""
    changes: list = []
    return _changes.set(changes), changes


def stop_capture(token):
    try:
        _changes.reset(token)
    except ValueError:
        _changes.set(None)


def finish(changes, *, method, path, query, status_code, duration_ms, headers, client_ip, body_bytes, content_type):
    changes = list(changes or [])
    try:
        body = None
        if body_bytes and "json" in (content_type or ""):
            try:
                body = json.dumps(redact(json.loads(body_bytes)), ensure_ascii=False, default=str)
            except ValueError:
                body = None
        elif "multipart" in (content_type or ""):
            body = json.dumps({"_note": "file upload / form (not stored)"})
        if body and len(body) > MAX_BODY:
            body = body[:MAX_BODY] + "…"

        user_id, username, role, impersonated_by = _who(headers)
        changes_text = json.dumps(changes, ensure_ascii=False, default=str) if changes else None
        if changes_text and len(changes_text) > 20000:
            changes_text = json.dumps(changes[:20], ensure_ascii=False, default=str)[:20000]

        db = SessionLocal()
        try:
            if user_id and not username:
                user = db.get(User, user_id)
                username = user.username if user else None
            db.add(
                ActivityLog(
                    user_id=user_id,
                    username=(username or "")[:50] or None,
                    role=(role or "")[:30] or None,
                    impersonated_by=impersonated_by,
                    method=method.upper()[:10],
                    path=path[:500],
                    query=(query or "")[:1000] or None,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    ip=(client_ip or "")[:64] or None,
                    user_agent=(headers.get("user-agent") or "")[:255] or None,
                    summary=summarize(changes, status_code),
                    body=body,
                    changes=changes_text,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.exception("System Logs: couldn't write the log row")


def prune_old_logs():
    """Keep RETENTION_DAYS of System Logs (run at startup)."""
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
        db.query(ActivityLog).filter(ActivityLog.created_at < cutoff).delete(
            synchronize_session=False
        )
        db.commit()
    except Exception:
        logger.exception("System Logs: prune failed")
        db.rollback()
    finally:
        db.close()
