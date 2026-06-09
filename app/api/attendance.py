import logging
import math
import pytz

from datetime import datetime, date
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
)
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.attendance import AttendanceRecord
from app.models.employees import Employee
from app.models.user import User
from app.models.trips import Trip
from app.models.trip_helper import TripHelper
from app.models.files import File as FileModel
from app.services.file_service import FileService
from app.services.face_recognition_service import FaceRecognitionService
from app.schemas.attendance import (
    AttendanceCreate,
    AttendanceResponse,
    AttendanceUpdate,
    BulkAttendanceMixed,
    AttendanceTimeAdjust,
)

router = APIRouter(prefix="/attendance", tags=["Attendance"])

logger = logging.getLogger("attendance")

PH_TZ = pytz.timezone("Asia/Manila")
UTC = pytz.utc

# Kiosk location - Tytan Corporation Yard
# KIOSK_ALLOWED_LATITUDE = 10.345240
# KIOSK_ALLOWED_LONGITUDE = 123.936819
# KIOSK_ALLOWED_RADIUS_METERS = 150

ATTENDANCE_ALLOWED_LOCATIONS = [
    {
        "name": "TPC Yard",
        "latitude": 10.345240,
        "longitude": 123.936819,
        "radius_meters": 150,
    },
    {
        "name": "Test Location",
        "latitude": 10.359618,
        "longitude": 123.973413,
        "radius_meters": 150,
    },
    {
        "name": "Consolacion Office",
        "latitude": 10.3787,
        "longitude": 123.9666,
        "radius_meters": 150,
    },
    {
        "name": "Mandaue Plant",
        "latitude": 10.3305,
        "longitude": 123.9333,
        "radius_meters": 150,
    },
]


def calculate_distance_meters(lat1, lon1, lat2, lon2):
    radius = 6371000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return radius * c


def find_nearest_allowed_attendance_location(
    latitude: float,
    longitude: float,
):
    nearest_location = None
    nearest_distance = None

    for location in ATTENDANCE_ALLOWED_LOCATIONS:
        distance = calculate_distance_meters(
            latitude,
            longitude,
            location["latitude"],
            location["longitude"],
        )

        if nearest_distance is None or distance < nearest_distance:
            nearest_distance = distance
            nearest_location = location

    if not nearest_location:
        return None, None, False

    allowed_radius = nearest_location["radius_meters"]

    is_allowed = nearest_distance <= allowed_radius

    return (
        nearest_location,
        nearest_distance,
        is_allowed,
    )


def format_attendance_time_only(value):
    if not value:
        return None

    if value.tzinfo is None:
        value = UTC.localize(value)

    ph_time = value.astimezone(PH_TZ)

    return ph_time.strftime("%I:%M %p")


def create_attendance_record(
    db: Session,
    employee_id: int,
    status: str,
    user_id: int | None,
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
        attendance_method="MANUAL",
        created_by_user_id=user_id,
    )

    db.add(record)
    return record


@router.post("/time-in-selfie", response_model=AttendanceResponse)
def time_in_selfie(
    latitude: float = Form(...),
    longitude: float = Form(...),
    address: str = Form(...),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ["admin", "superadmin", "motorpool"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    employee_id = current_user.employee_id

    if not employee_id:
        raise HTTPException(
            status_code=400,
            detail="User account is not linked to an employee.",
        )

    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Photo must be an image file")

    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    now = datetime.utcnow()
    today = datetime.now(ZoneInfo("Asia/Manila")).date()

    existing = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.attendance_date == today,
        )
        .first()
    )

    if existing and existing.check_in_time:
        raise HTTPException(
            status_code=400,
            detail="Employee already timed in today",
        )

    record = existing or AttendanceRecord(
        employee_id=employee_id,
        attendance_date=today,
        status="Present",
        attendance_method="SELFIE",
        created_by_user_id=current_user.id,
    )

    record.check_in_time = now
    record.time_in_latitude = latitude
    record.time_in_longitude = longitude
    record.time_in_address = address

    if not existing:
        db.add(record)
        db.flush()

    file_service = FileService()
    photo_url = file_service.upload(photo, f"attendance/{record.id}/time-in")

    db.add(
        FileModel(
            entity_type="attendance",
            entity_id=record.id,
            document_type="ATTENDANCE_TIME_IN",
            file_url=photo_url,
            uploaded_by=current_user.id,
        )
    )

    db.commit()
    db.refresh(record)

    record.time_in_photo_url = photo_url
    record.time_out_photo_url = None

    return record


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


@router.get("/today")
def get_my_attendance_today(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.employee_id:
        raise HTTPException(
            status_code=400,
            detail="User account is not linked to an employee.",
        )

    today = datetime.now(ZoneInfo("Asia/Manila")).date()

    record = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == current_user.employee_id,
            AttendanceRecord.attendance_date == today,
        )
        .first()
    )

    if not record:
        return {
            "has_record": False,
            "check_in_time": None,
            "check_out_time": None,
            "status": None,
        }

    return {
        "has_record": True,
        "id": record.id,
        "attendance_date": str(record.attendance_date),
        "check_in_time": format_attendance_time_only(record.check_in_time),
        "check_out_time": format_attendance_time_only(record.check_out_time),
        "status": record.status,
        "time_in_latitude": record.time_in_latitude,
        "time_in_longitude": record.time_in_longitude,
        "time_in_address": record.time_in_address,
    }


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


@router.get("/list")
def get_attendance_records(
    skip: int = 0,
    limit: int = 5000,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sync_trip_attendance_records(db, current_user.id)

    records = (
        db.query(AttendanceRecord)
        .order_by(AttendanceRecord.attendance_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    valid_statuses = ["COMPLETED", "completed", "APPROVED", "approved"]

    response = []

    for record in records:
        employee = db.query(Employee).filter(Employee.id == record.employee_id).first()

        employee_name = "Unknown Employee"
        employee_department = None

        if employee:
            employee_name = " ".join(
                filter(
                    None,
                    [
                        employee.first_name,
                        getattr(employee, "middle_name", None),
                        employee.last_name,
                        getattr(employee, "suffix", None),
                    ],
                )
            )

            employee_department = employee.department

        profile_photo = (
            db.query(FileModel)
            .filter(
                FileModel.entity_type == "employee",
                FileModel.entity_id == record.employee_id,
                FileModel.document_type == "PROFILE_IMAGE",
            )
            .first()
        )

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

        time_in_photo = (
            db.query(FileModel)
            .filter(
                FileModel.entity_type == "attendance",
                FileModel.entity_id == record.id,
                FileModel.document_type == "ATTENDANCE_TIME_IN",
            )
            .first()
        )

        time_out_photo = (
            db.query(FileModel)
            .filter(
                FileModel.entity_type == "attendance",
                FileModel.entity_id == record.id,
                FileModel.document_type == "ATTENDANCE_TIME_OUT",
            )
            .first()
        )

        response.append(
            {
                "id": record.id,
                "employee_id": record.employee_id,
                "employee_name": employee_name,
                "employee_department": employee_department,
                "department": employee_department,
                "profile_photo_url": profile_photo.file_url if profile_photo else None,
                "attendance_date": (
                    str(record.attendance_date) if record.attendance_date else None
                ),
                "check_in_time": format_attendance_time_only(record.check_in_time),
                "check_out_time": format_attendance_time_only(record.check_out_time),
                "check_in_time_raw": (
                    record.check_in_time.isoformat() if record.check_in_time else None
                ),
                "check_out_time_raw": (
                    record.check_out_time.isoformat() if record.check_out_time else None
                ),
                "time_in_latitude": record.time_in_latitude,
                "time_in_longitude": record.time_in_longitude,
                "time_in_address": record.time_in_address,
                "time_out_latitude": record.time_out_latitude,
                "time_out_longitude": record.time_out_longitude,
                "time_out_address": record.time_out_address,
                "time_in_photo_url": time_in_photo.file_url if time_in_photo else None,
                "time_out_photo_url": (
                    time_out_photo.file_url if time_out_photo else None
                ),
                "face_match_score": record.face_match_score,
                "face_review_status": record.face_review_status,
                "face_review_reason": record.face_review_reason,
                "face_checked_at": record.face_checked_at,
                "reviewed_by_user_id": record.reviewed_by_user_id,
                "reviewed_at": record.reviewed_at,
                "attendance_method": record.attendance_method,
                "status": record.status,
                "created_by_user_id": record.created_by_user_id,
                "completed_trips": (driver_trip_count or 0) + (helper_trip_count or 0),
            }
        )

    return response


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
        raise HTTPException(status_code=404, detail="Attendance record not found")

    if record.status == attendance_in.status:
        raise HTTPException(
            status_code=400,
            detail="Attendance status is already the same.",
        )

    record.status = attendance_in.status

    db.commit()
    db.refresh(record)

    return record


@router.get("/kiosk/status/{employee_id}")
def get_kiosk_attendance_status(
    employee_id: int,
    db: Session = Depends(get_db),
):
    logger.info("KIOSK STATUS ENDPOINT HIT")
    logger.info(f"EMPLOYEE ID RECEIVED: {employee_id}")

    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id, Employee.is_active == 1)
        .first()
    )

    logger.info(f"EMPLOYEE RESULT: {employee}")

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found or inactive.",
        )

    today = datetime.now(ZoneInfo("Asia/Manila")).date()

    record = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.attendance_date == today,
        )
        .first()
    )

    logger.info(f"ATTENDANCE RECORD: {record}")

    employee_name = " ".join(
        filter(
            None,
            [
                employee.first_name,
                getattr(employee, "middle_name", None),
                employee.last_name,
                getattr(employee, "suffix", None),
            ],
        )
    )

    if not record:
        return {
            "employee_id": employee.id,
            "employee_name": employee_name,
            "has_record": False,
            "has_timed_in": False,
            "has_timed_out": False,
            "time_in": None,
            "time_out": None,
            "next_action": "time_in",
            "message": "Ready for time in.",
        }

    has_timed_in = record.check_in_time is not None
    has_timed_out = record.check_out_time is not None

    if has_timed_in and not has_timed_out:
        next_action = "time_out"
        message = "Employee already timed in. Ready for time out."
    elif has_timed_in and has_timed_out:
        next_action = "completed"
        message = "Attendance already completed for today."
    else:
        next_action = "time_in"
        message = "Ready for time in."

    return {
        "employee_id": employee.id,
        "employee_name": employee_name,
        "has_record": True,
        "has_timed_in": has_timed_in,
        "has_timed_out": has_timed_out,
        "time_in": format_attendance_time_only(record.check_in_time),
        "time_out": format_attendance_time_only(record.check_out_time),
        "next_action": next_action,
        "message": message,
    }


@router.post("/kiosk/selfie")
def kiosk_selfie_attendance(
    employee_id: int = Form(...),
    action: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    address: str = Form(...),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    logger.info("KIOSK SELFIE ENDPOINT HIT")
    logger.info(f"EMPLOYEE ID: {employee_id}")
    logger.info(f"ACTION: {action}")
    logger.info(f"LATITUDE: {latitude}")
    logger.info(f"LONGITUDE: {longitude}")
    logger.info(f"ADDRESS: {address}")
    logger.info(f"PHOTO NAME: {photo.filename}")
    logger.info(f"PHOTO TYPE: {photo.content_type}")

    if action not in ["time_in", "time_out"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid action. Use time_in or time_out.",
        )

    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Photo must be an image file.")

    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id, Employee.is_active == 1)
        .first()
    )

    logger.info(f"EMPLOYEE RESULT: {employee}")

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found or inactive.",
        )

    nearest_location, distance_meters, is_allowed_location = (
        find_nearest_allowed_attendance_location(
            latitude,
            longitude,
        )
    )

    logger.info(
        f"LOCATION CHECK | "
        f"NEAREST={nearest_location['name']} | "
        f"DISTANCE={round(distance_meters, 2)}"
    )

    if not is_allowed_location:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Attendance rejected. "
                f"You are {round(distance_meters, 2)} meters away from "
                f"{nearest_location['name']}. "
                f"Allowed radius is "
                f"{nearest_location['radius_meters']} meters."
            ),
        )

    now = datetime.utcnow()
    today = datetime.now(ZoneInfo("Asia/Manila")).date()

    record = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.attendance_date == today,
        )
        .first()
    )

    logger.info(f"EXISTING ATTENDANCE: {record}")

    if action == "time_in":
        if record and record.check_in_time:
            raise HTTPException(
                status_code=400,
                detail="Employee already timed in today.",
            )

        if not record:
            record = AttendanceRecord(
                employee_id=employee_id,
                attendance_date=today,
                status="Present",
                attendance_method="KIOSK_SELFIE",
                created_by_user_id=None,
            )
            db.add(record)
            db.flush()

        record.check_in_time = now
        record.time_in_latitude = latitude
        record.time_in_longitude = longitude
        record.time_in_address = address
        record.attendance_method = "KIOSK_SELFIE"

        document_type = "ATTENDANCE_TIME_IN"
        upload_folder = f"attendance/{record.id}/time-in"

    else:
        if not record or not record.check_in_time:
            raise HTTPException(
                status_code=400,
                detail="Employee has not timed in yet.",
            )

        if record.check_out_time:
            raise HTTPException(
                status_code=400,
                detail="Employee already timed out today.",
            )

        record.check_out_time = now
        record.time_out_latitude = latitude
        record.time_out_longitude = longitude
        record.time_out_address = address
        record.attendance_method = "KIOSK_SELFIE"

        document_type = "ATTENDANCE_TIME_OUT"
        upload_folder = f"attendance/{record.id}/time-out"

    file_service = FileService()
    photo_url = file_service.upload(photo, upload_folder)

    if action == "time_in":
        profile_photo = (
            db.query(FileModel)
            .filter(
                FileModel.entity_type == "employee",
                FileModel.entity_id == employee_id,
                FileModel.document_type == "PROFILE_IMAGE",
            )
            .first()
        )

        face_service = FaceRecognitionService()

        face_result = face_service.compare_faces(
            profile_photo_url=profile_photo.file_url if profile_photo else None,
            attendance_photo_url=photo_url,
        )

        record.face_match_score = face_result["score"]
        record.face_review_status = face_result["status"]
        record.face_review_reason = face_result["reason"]
        record.face_checked_at = face_result["checked_at"]

    logger.info(f"PHOTO URL: {photo_url}")

    db.add(
        FileModel(
            entity_type="attendance",
            entity_id=record.id,
            document_type=document_type,
            file_url=photo_url,
            uploaded_by=None,
        )
    )

    db.commit()
    db.refresh(record)

    logger.info("KIOSK ATTENDANCE SUCCESS")

    return {
        "message": (
            "Time in successful." if action == "time_in" else "Time out successful."
        ),
        "attendance_id": record.id,
        "employee_id": record.employee_id,
        "attendance_date": str(record.attendance_date),
        "check_in_time": format_attendance_time_only(record.check_in_time),
        "check_out_time": format_attendance_time_only(record.check_out_time),
        "photo_url": photo_url,
        "next_action": "time_out" if action == "time_in" else "completed",
        "distance_meters": round(distance_meters, 2),
        "allowed_radius_meters": nearest_location["radius_meters"],
        "nearest_allowed_location": nearest_location["name"],
        "face_match_score": record.face_match_score,
        "face_review_status": record.face_review_status,
        "face_review_reason": record.face_review_reason,
    }


# approve and reject endpoint for face review will be created separately
@router.post("/{attendance_id}/approve")
def approve_attendance(
    attendance_id: int,
    db: Session = Depends(get_db),
):
    attendance = (
        db.query(AttendanceRecord).filter(AttendanceRecord.id == attendance_id).first()
    )

    if not attendance:
        raise HTTPException(status_code=404, detail="Attendance record not found.")

    attendance.face_review_status = "APPROVED"

    db.commit()
    db.refresh(attendance)

    return {
        "message": "Attendance approved.",
        "attendance_id": attendance.id,
        "status": attendance.face_review_status,
    }


@router.post("/{attendance_id}/reject")
def reject_attendance(
    attendance_id: int,
    db: Session = Depends(get_db),
):
    attendance = (
        db.query(AttendanceRecord).filter(AttendanceRecord.id == attendance_id).first()
    )

    if not attendance:
        raise HTTPException(status_code=404, detail="Attendance record not found.")

    attendance.face_review_status = "REJECTED"

    db.commit()
    db.refresh(attendance)

    return {
        "message": "Attendance rejected.",
        "attendance_id": attendance.id,
        "status": attendance.face_review_status,
    }


@router.patch("/{attendance_id}/adjust-time")
def adjust_attendance_time(
    attendance_id: int,
    payload: AttendanceTimeAdjust,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Only Admin and Superadmin can modify attendance
    if current_user.role not in [
        "admin",
        "superadmin",
    ]:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to adjust attendance.",
        )

    attendance = (
        db.query(AttendanceRecord).filter(AttendanceRecord.id == attendance_id).first()
    )

    if not attendance:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found.",
        )

    print("PAYLOAD IN:", payload.check_in_time)
    print("PAYLOAD OUT:", payload.check_out_time)

    try:
        if payload.check_in_time:
            local_dt = datetime.strptime(
                payload.check_in_time,
                "%Y-%m-%d %H:%M:%S",
            )

            local_dt = PH_TZ.localize(local_dt)

            attendance.check_in_time = local_dt.astimezone(UTC)

        if payload.check_out_time:
            local_dt = datetime.strptime(
                payload.check_out_time,
                "%Y-%m-%d %H:%M:%S",
            )

            local_dt = PH_TZ.localize(local_dt)

            attendance.check_out_time = local_dt.astimezone(UTC)

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=("Invalid datetime format. " "Use YYYY-MM-DD HH:MM:SS"),
        )

    db.commit()
    db.refresh(attendance)

    return {
        "message": "Attendance adjusted successfully.",
        "attendance_id": attendance.id,
        "check_in_time": attendance.check_in_time,
        "check_out_time": attendance.check_out_time,
    }
