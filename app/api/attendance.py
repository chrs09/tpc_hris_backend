from datetime import datetime, date
from typing import List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.attendance import AttendanceRecord
from app.models.employees import Employee
from app.models.user import User
from app.models.trips import Trip
from app.models.trip_helper import TripHelper
from app.schemas.attendance import (
    AttendanceCreate,
    AttendanceResponse,
    AttendanceUpdate,
    BulkAttendanceMixed,
)

router = APIRouter(prefix="/attendance", tags=["Attendance"])


# -------------------------------
# Helper: Create attendance record
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
        check_in_time=datetime.utcnow(),
        created_by_user_id=user_id,
    )

    db.add(record)
    return record


# -------------------------------
# Helper: Auto-create attendance from trips
# -------------------------------
def sync_trip_attendance_records(db: Session, user_id: int):
    valid_statuses = ["COMPLETED", "completed", "APPROVED", "approved"]

    trips = (
        db.query(Trip)
        .filter(
            Trip.status.in_(valid_statuses),
            Trip.driver_id.isnot(None),
            Trip.start_time.isnot(None),
        )
        .all()
    )

    created_count = 0

    for trip in trips:
        trip_date = trip.start_time.date()

        # -----------------------------
        # 1. Create DRIVER attendance
        # -----------------------------
        driver_user = db.query(User).filter(User.id == trip.driver_id).first()

        if driver_user and driver_user.employee_id:
            existing_driver_attendance = (
                db.query(AttendanceRecord)
                .filter(
                    AttendanceRecord.employee_id == driver_user.employee_id,
                    AttendanceRecord.attendance_date == trip_date,
                )
                .first()
            )

            if not existing_driver_attendance:
                db.add(
                    AttendanceRecord(
                        employee_id=driver_user.employee_id,
                        status="Present",
                        attendance_date=trip_date,
                        check_in_time=trip.start_time,
                        created_by_user_id=user_id,
                    )
                )
                created_count += 1

        # -----------------------------
        # 2. Create HELPER attendance
        # -----------------------------
        trip_helpers = db.query(TripHelper).filter(TripHelper.trip_id == trip.id).all()

        for trip_helper in trip_helpers:
            existing_helper_attendance = (
                db.query(AttendanceRecord)
                .filter(
                    AttendanceRecord.employee_id == trip_helper.helper_id,
                    AttendanceRecord.attendance_date == trip_date,
                )
                .first()
            )

            if existing_helper_attendance:
                continue

            db.add(
                AttendanceRecord(
                    employee_id=trip_helper.helper_id,
                    status="Present",
                    attendance_date=trip_date,
                    check_in_time=trip.start_time,
                    created_by_user_id=user_id,
                )
            )
            created_count += 1

    if created_count > 0:
        db.commit()


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

    today = datetime.now(ZoneInfo("Asia/Manila")).date()

    if attendance_in.attendance_date > today:
        raise HTTPException(
            status_code=403,
            detail="Cannot record attendance for future dates.",
        )

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
            detail="Attendance already recorded for this date.",
        )

    db.commit()
    db.refresh(record)

    return record


# -------------------------------
# Bulk mixed attendance
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
    today = datetime.now(ZoneInfo("Asia/Manila")).date()

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


# -------------------------------
# Get attendance records
# -------------------------------
@router.get("/list", response_model=List[AttendanceResponse])
def get_attendance_records(
    skip: int = 0,
    limit: int = 5000,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Auto-create missing attendance rows from approved/completed trips
    sync_trip_attendance_records(db, current_user.id)

    records = (
        db.query(AttendanceRecord)
        .order_by(AttendanceRecord.attendance_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    valid_statuses = [
        "COMPLETED",
        "completed",
        "APPROVED",
        "approved",
    ]

    for record in records:

        # ---------------------------------------
        # DRIVER TRIPS
        # Trip.driver_id -> User.id
        # User.employee_id -> Employee.id
        # ---------------------------------------
        driver_trip_count = (
            db.query(func.count(Trip.id))
            .join(User, User.id == Trip.driver_id)
            .filter(
                User.employee_id == record.employee_id,
                Trip.status.in_(valid_statuses),
                func.date(Trip.start_time) == record.attendance_date,
            )
            .scalar()
        )

        # ---------------------------------------
        # HELPER TRIPS
        # TripHelper.helper_id -> Employee.id
        # ---------------------------------------
        helper_trip_count = (
            db.query(func.count(Trip.id))
            .join(TripHelper, TripHelper.trip_id == Trip.id)
            .filter(
                TripHelper.helper_id == record.employee_id,
                Trip.status.in_(valid_statuses),
                func.date(Trip.start_time) == record.attendance_date,
            )
            .scalar()
        )

        # ---------------------------------------
        # TOTAL TRIPS
        # ---------------------------------------
        record.completed_trips = (driver_trip_count or 0) + (helper_trip_count or 0)

    return records


# -------------------------------
# Update attendance record
# -------------------------------
@router.patch("/update", response_model=AttendanceResponse)
def update_attendance(
    attendance_in: AttendanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = datetime.now(ZoneInfo("Asia/Manila")).date()

    if current_user.role != "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Only superadmin can edit attendance records.",
        )

    if attendance_in.attendance_date > today:
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

    if record.status == attendance_in.status:
        raise HTTPException(
            status_code=400,
            detail="Attendance status is already the same.",
        )

    record.status = attendance_in.status

    db.commit()
    db.refresh(record)

    return record
