from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.core.database import Base


class ErrorLog(Base):
    """Persisted copy of every error alert also posted to Slack (see
    send_error_alert/send_response_alert in app/services/slack_service.py
    and the exception handlers in app/main.py) -- lets superadmin browse
    the history in the app itself instead of scrolling Slack."""

    __tablename__ = "tpc_error_logs"

    id = Column(Integer, primary_key=True, index=True)

    method = Column(String(10), nullable=False)
    url = Column(String(2048), nullable=False)
    status_code = Column(Integer, nullable=False)

    # Populated for an unhandled exception (500); null for a plain
    # HTTPException/validation error, which has no exception type of its
    # own beyond "the endpoint raised this status on purpose".
    error_type = Column(String(255), nullable=True)

    detail = Column(Text, nullable=True)
    traceback = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
