from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from app.core.database import get_db
from app.models import Employee, AttendanceRecord

router = APIRouter()

@router.get("/dashboard/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):

    today = date.today()

    total_employees = db.query(Employee).count()

    attendance_counts = db.query(
        AttendanceRecord.status,
        func.count(AttendanceRecord.id)
    ).filter(
        func.date(AttendanceRecord.check_in_time) == today
    ).group_by(
        AttendanceRecord.status
    ).all()

    summary = {
        "Present": 0,
        "Absent": 0,
        "On Leave": 0
    }

    for status, count in attendance_counts:
        summary[status] = count

    return {
        "total_employees": total_employees,
        "present": summary["Present"],
        "absent": summary["Absent"],
        "on_leave": summary["On Leave"]
    }