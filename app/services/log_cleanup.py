"""Keeps the log tables small.

- Error Logs: this month and last month are kept; older rows are deleted
  (they're also in Slack's #production-errors).
- System Logs: kept 180 days (activity_log_service.RETENTION_DAYS).

Runs once a day in a background thread (started from app/main.py), so it
happens even when the server isn't restarted for weeks. Superadmin can
also delete older Error Logs from the page (app/api/error_logs.py).
"""

import logging
import threading
import time as time_module
from datetime import date, datetime, time, timedelta

from app.core.database import SessionLocal
from app.models.error_log import ErrorLog

logger = logging.getLogger("log_cleanup")

PH_OFFSET = timedelta(hours=8)
RUN_EVERY_SECONDS = 24 * 60 * 60
_started = False


def ph_today() -> date:
    return (datetime.utcnow() + PH_OFFSET).date()


def month_start(day: date, months_back: int = 0) -> date:
    """The 1st of the month `months_back` months before `day`'s month."""
    year, month = day.year, day.month - months_back
    while month < 1:
        month += 12
        year -= 1
    return date(year, month, 1)


def ph_day_to_utc(day: date) -> datetime:
    """Midnight at the start of a PH day, as naive UTC (how rows are stored)."""
    return datetime.combine(day, time.min) - PH_OFFSET


def default_error_log_cutoff() -> date:
    """Keep this month and last month: delete before the 1st of last month."""
    return month_start(ph_today(), 1)


def delete_error_logs_before(day: date) -> int:
    db = SessionLocal()
    try:
        count = (
            db.query(ErrorLog)
            .filter(ErrorLog.created_at < ph_day_to_utc(day))
            .delete(synchronize_session=False)
        )
        db.commit()
        return count
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_cleanup_once() -> None:
    from app.services.activity_log_service import prune_old_logs

    try:
        removed = delete_error_logs_before(default_error_log_cutoff())
        if removed:
            logger.info("Error Logs: removed %s rows older than last month", removed)
    except Exception as exc:
        logger.warning("Error Logs cleanup failed: %s", exc)
    prune_old_logs()


def start_log_cleanup() -> None:
    """Daemon thread: clean up shortly after start, then once a day."""
    global _started
    if _started:
        return
    _started = True

    def loop():
        time_module.sleep(120)
        while True:
            run_cleanup_once()
            time_module.sleep(RUN_EVERY_SECONDS)

    threading.Thread(target=loop, name="log-cleanup", daemon=True).start()
