from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.database import get_db
from app.models import Employee, AttendanceRecord

router = APIRouter()

philippines = ZoneInfo("Asia/Manila")
utc = ZoneInfo("UTC")


@router.get("/dashboard/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):

    # Current PH time
    now_ph = datetime.now(philippines)

    # PH start & end of day
    start_ph = now_ph.replace(hour=0, minute=0, second=0, microsecond=0)
    end_ph = start_ph + timedelta(days=1)

    # Convert PH range to UTC (because DB stores UTC)
    start_utc = start_ph.astimezone(utc)
    end_utc = end_ph.astimezone(utc)

    total_employees = db.query(Employee).count()

    attendance_counts = (
        db.query(AttendanceRecord.status, func.count(AttendanceRecord.id))
        .filter(
            AttendanceRecord.check_in_time >= start_utc,
            AttendanceRecord.check_in_time < end_utc,
        )
        .group_by(AttendanceRecord.status)
        .all()
    )

    summary = {"Present": 0, "Absent": 0, "On Leave": 0}

    for status, count in attendance_counts:
        if status in summary:
            summary[status] = count

    return {
        "total_employees": total_employees,
        "present": summary["Present"],
        "absent": summary["Absent"],
        "on_leave": summary["On Leave"],
    }
