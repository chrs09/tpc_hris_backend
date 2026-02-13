from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.models.attendance import AttendanceRecord
from app.models.employees import Employee
from app.models.user import User
from app.schemas.attendance import (
    AttendanceResponse,
    AttendanceCreate,
    BulkAttendanceMixed,
)
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/attendance", tags=["Attendance"])


# -------------------------------
# Helper function
# -------------------------------
def create_attendance_record(
    db: Session,
    employee_id: int,
    status: str,
    user_id: int,
    check_in_time: datetime | None = None,
):
    record = AttendanceRecord(
        employee_id=employee_id,
        status=status,
        check_in_time=check_in_time or datetime.utcnow(),
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

    record = create_attendance_record(
        db=db,
        employee_id=employee.id,
        status=attendance_in.status,
        user_id=current_user.id,
        check_in_time=attendance_in.check_in_time,
    )

    db.commit()
    db.refresh(record)

    return record


# -------------------------------
# Bulk by department
# -------------------------------
@router.post("/bulk/", response_model=List[AttendanceResponse])
def bulk_mark_attendance(
    department: str,
    status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employees = db.query(Employee).filter_by(department=department, is_active=1).all()
    if not employees:
        raise HTTPException(status_code=404, detail="No employees found in this department")

    records = [
        create_attendance_record(
            db=db,
            employee_id=emp.id,
            status=status,
            user_id=current_user.id,
        )
        for emp in employees
    ]

    db.commit()
    for record in records:
        db.refresh(record)

    return records


# -------------------------------
# Bulk mixed (different status per employee)
# -------------------------------
@router.post("/bulk-mixed/", response_model=List[AttendanceResponse])
def bulk_mixed_attendance(
    attendance_in: BulkAttendanceMixed,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee_ids = [att.employee_id for att in attendance_in.attendances]

    employees = db.query(Employee).filter(Employee.id.in_(employee_ids), Employee.is_active == 1).all()
    print("Found employees in DB:", [(emp.id, emp.first_name, emp.is_active) for emp in employees])  
    # employees = (
    #     db.query(Employee)
    #     .filter(Employee.id.in_(employee_ids))
    #     .all()
    # )

    if not employees:
        raise HTTPException(status_code=404, detail="No valid employees found")

    valid_employee_ids = {emp.id for emp in employees}

    records = []

    for att in attendance_in.attendances:
        if att.employee_id not in valid_employee_ids:
            continue

        record = create_attendance_record(
            db=db,
            employee_id=att.employee_id,
            status=att.status,
            user_id=current_user.id,
        )
        records.append(record)

    if not records:
        raise HTTPException(status_code=400, detail="No attendance records created")

    db.commit()
    for record in records:
        db.refresh(record)

    return records

@router.get("/list", response_model=List[AttendanceResponse])
def get_attendance_records(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    records = db.query(AttendanceRecord).offset(skip).limit(limit).all()
    return records