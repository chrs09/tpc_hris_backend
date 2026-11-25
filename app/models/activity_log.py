from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.core.database import Base


class ActivityLog(Base):
    """System Logs (superadmin only): one row per change request -- every
    POST / PUT / PATCH / DELETE that reached the API -- with who sent it,
    the URL, what was sent (passwords and tokens hidden), the result, and
    the database rows it changed (old -> new). Written by
    app/services/activity_log_service.py; read by app/api/system_logs.py."""

    __tablename__ = "tpc_activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Who: username/role are copied so the log still reads right after the
    # account is renamed or removed. impersonated_by = the superadmin who
    # was using "View As" at the time.
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String(50), nullable=True)
    role = Column(String(30), nullable=True)
    impersonated_by = Column(Integer, nullable=True)

    method = Column(String(10), nullable=False)
    path = Column(String(500), nullable=False, index=True)
    query = Column(String(1000), nullable=True)
    status_code = Column(Integer, nullable=False)
    duration_ms = Column(Integer, nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)

    # Short line for the table, e.g. "Updated attendance #12 (status, remarks)".
    summary = Column(String(255), nullable=True)
    # Request body as JSON text (secrets hidden, trimmed).
    body = Column(Text, nullable=True)
    # JSON list of {action, table, id, fields: {name: [old, new]}}.
    changes = Column(Text, nullable=True)
