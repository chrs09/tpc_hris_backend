from datetime import datetime, date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.attendance import AttendanceRecord
from app.models.employees import Employee
from app.models.user import User
from app.schemas.attendance import (
    AttendanceCreate,
    AttendanceResponse,
    AttendanceUpdate,
    BulkAttendanceMixed,
)

router = APIRouter(prefix="/attendance", tags=["Attendance"])


# -------------------------------
# Helper function
# -------------------------------


def create_attendance_record(
    db: Session,
    employee_id: int,
    status: str,
    user_id: int,
    attendance_date: date,
):
    existing = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.attendance_date == attendance_date,
        )
        .first()
    )

    if existing:
        return None

    record = AttendanceRecord(
        employee_id=employee_id,
        status=status,
        attendance_date=attendance_date,
        check_in_time=datetime.utcnow(),  # audit only
        created_by_user_id=user_id,
    )

    db.add(record)
    return record


# -------------------------------
# Single attendance
# -------------------------------


@router.post("/", response_model=AttendanceResponse)
def mark_attendance(
    attendance_in: AttendanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = db.query(Employee).filter_by(id=attendance_in.employee_id).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # today = date.today()

    record = create_attendance_record(
        db=db,
        employee_id=employee.id,
        status=attendance_in.status,
        user_id=current_user.id,
        attendance_date=attendance_in.attendance_date,
    )

    if not record:
        raise HTTPException(
            status_code=400,
            detail="Attendance already recorded for today.",
        )

    db.commit()
    db.refresh(record)

    return record


# -------------------------------
# Bulk mixed (different status per employee)
# -------------------------------
@router.post("/bulk-mixed/")
def bulk_mixed_attendance(
    attendance_in: BulkAttendanceMixed,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee_ids = [att.employee_id for att in attendance_in.attendances]

    employees = (
        db.query(Employee)
        .filter(Employee.id.in_(employee_ids), Employee.is_active == 1)
        .all()
    )

    if not employees:
        raise HTTPException(status_code=404, detail="No valid employees found")

    valid_employee_ids = {emp.id for emp in employees}
    today = date.today()

    saved_records = []
    skipped_employee_ids = []

    for att in attendance_in.attendances:
        if att.employee_id not in valid_employee_ids:
            continue

        record = create_attendance_record(
            db=db,
            employee_id=att.employee_id,
            status=att.status,
            user_id=current_user.id,
            attendance_date=today,
        )

        if record:
            saved_records.append(record)
        else:
            skipped_employee_ids.append(att.employee_id)

    if not saved_records:
        raise HTTPException(
            status_code=400,
            detail="All selected employees already have attendance for today.",
        )

    db.commit()

    for record in saved_records:
        db.refresh(record)

    return {
        "saved_count": len(saved_records),
        "skipped_count": len(skipped_employee_ids),
        "skipped_employee_ids": skipped_employee_ids,
    }


@router.get("/list", response_model=List[AttendanceResponse])
def get_attendance_records(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    records = (
        db.query(AttendanceRecord)
        .order_by(AttendanceRecord.attendance_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return records


# -------------------------------
# Update attendance record (for editing)
# -------------------------------
@router.patch("/update", response_model=AttendanceResponse)
def update_attendance(
    attendance_in: AttendanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 🚫 Only superadmin can edit
    if current_user.role != "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Not allowed to edit attendance records.",
        )

    # 🚫 Cannot edit today or future
    if attendance_in.attendance_date > date.today():
        raise HTTPException(
            status_code=403,
            detail="Only past attendance can be edited.",
        )

    record = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == attendance_in.employee_id,
            AttendanceRecord.attendance_date == attendance_in.attendance_date,
        )
        .first()
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found",
        )

    # 🚫 Prevent unnecessary overwrite
    if record.status == attendance_in.status:
        raise HTTPException(
            status_code=400,
            detail="Attendance status is already the same.",
        )

    record.status = attendance_in.status

    db.commit()
    db.refresh(record)

    return record
