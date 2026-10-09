import logging
import math
import pytz

from collections import defaultdict
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from fastapi import (
    Body,
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Query,
)
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    has_editable_grant,
    require_role_or_module,
    require_superadmin,
    require_superadmin_or_editable,
)
from app.models.attendance import AttendanceRecord
from app.models.attendance_adjustment import AttendanceAdjustment
from app.utils.user_display import display_name
from app.models.employees import Employee
from app.models.user import User
from app.models.trips import Trip
from app.models.trip_helper import TripHelper
from app.models.files import File as FileModel
from app.services.trip_rates import load_rules, resolve_trip_rates
from app.services.payroll_lock import ensure_unlocked
from app.services.file_service import FileService, _watermark_timestamp
from app.services.face_recognition_service import FaceRecognitionService
from app.services.photo_orientation import PHOTO_SIDES, rescore_side, rotate_stored_photo
from app.services.approval_chain import (
    acting_index,
    team_scope as _team_scope,
    effective_step,
    log_skipped,
    can_view_all_payroll,
    team_scope,
    append_log,
    describe_chain,
    dump_chain,
    load_json_list,
    resolve_chain,
)
from app.schemas.attendance import (
    AttendanceCreate,
    AttendanceResponse,
    AttendanceUpdate,
    BulkAttendanceMixed,
    AttendanceTimeAdjust,
)

from app.utils.timezone import utc_to_ph, utc_to_ph_date
from pydantic import BaseModel

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
        "radius_meters": 350,
    },
    {
        "name": "Cordova",
        "latitude": 10.2545,
        "longitude": 123.9487,
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


def check_attendance_geofence(latitude: float, longitude: float):
    """Where a time in/out happened relative to the allowed attendance
    locations. Never refuses -- returns (outside, note, photo_label):
    `note` explains the flag for reviewers, `photo_label` is the line
    burned onto the selfie (same watermark as the driver photos)."""
    nearest, distance, allowed = find_nearest_allowed_attendance_location(
        latitude, longitude
    )
    if not nearest:
        return True, "Outside geofence (no attendance locations set up).", (
            "Outside geofence"
        )
    meters = int(round(distance))
    if allowed:
        return False, None, f"{nearest['name']} ({meters}m)"
    return (
        True,
        (
            f"Outside geofence: {meters}m from {nearest['name']} "
            f"(allowed {nearest['radius_meters']}m)."
        ),
        f"Outside geofence - nearest: {nearest['name']} ({meters}m)",
    )


def flag_side_for_geofence(record, side: str, outside: bool, note: str | None):
    """Saves the geofence result on one side of the record and, when
    outside, sends that side to the existing review (Approve/Reject on
    the Attendance grid) -- keeping any face-check problem already there
    and adding the geofence reason in front of it."""
    setattr(record, f"{side}_outside_geofence", outside)
    setattr(record, f"{side}_geofence_note", note)
    if not outside:
        return
    status = getattr(record, f"{side}_face_review_status")
    reason = getattr(record, f"{side}_face_review_reason")
    if status not in ("NEEDS_REVIEW", "FACE_MATCH_FAILED", "NO_PROFILE_PHOTO"):
        setattr(record, f"{side}_face_review_status", "NEEDS_REVIEW")
    setattr(
        record,
        f"{side}_face_review_reason",
        f"{note} {reason}".strip() if reason else note,
    )


# A side in one of these still needs someone to approve or reject it.
# MISSED_TIME_OUT: forgot to time out -- the time they say they left is
# waiting for the attendance approvers (see file_missed_time_out).
REVIEW_PENDING_STATUSES = (
    "NEEDS_REVIEW",
    "FACE_MATCH_FAILED",
    "NO_PROFILE_PHOTO",
    "MISSED_TIME_OUT",
)

# =========================
# MISSED TIME OUT -- forgot to time out. At their next time in (phone or
# kiosk) they must first enter when they left and why; that goes to the
# Org Chart attendance approvers, who can change the time and approve
# (only then is the time out saved). A head can also set it themselves
# before it's filed (Approvals -> Attendance).
# =========================
MISSED_LOOKBACK_DAYS = 7
# Self-clocked days only -- drivers' attendance comes from their trips.
SELF_CLOCKED_METHODS = ("SELFIE", "KIOSK_SELFIE")


def _ph_today() -> date:
    return datetime.now(ZoneInfo("Asia/Manila")).date()


def missed_time_out_query(db: Session):
    """Open self-clocked days in the look-back window, not yet filed."""
    today = _ph_today()
    return db.query(AttendanceRecord).filter(
        AttendanceRecord.attendance_date < today,
        AttendanceRecord.attendance_date >= today - timedelta(days=MISSED_LOOKBACK_DAYS),
        AttendanceRecord.check_in_time.isnot(None),
        AttendanceRecord.check_out_time.is_(None),
        AttendanceRecord.missed_out_filed_at.is_(None),
        AttendanceRecord.attendance_method.in_(SELF_CLOCKED_METHODS),
    )


def _is_locked(db: Session, record) -> bool:
    """A day inside locked / paid payroll can't be changed any more, so
    it isn't asked for (HR handles it)."""
    try:
        ensure_unlocked(db, record.employee_id, record.attendance_date, "attendance")
        return False
    except HTTPException:
        return True


def open_missed_records(db: Session, employee_id: int | None = None) -> list:
    query = missed_time_out_query(db)
    if employee_id is not None:
        query = query.filter(AttendanceRecord.employee_id == employee_id)
    records = query.order_by(AttendanceRecord.attendance_date.asc()).all()
    return [r for r in records if not _is_locked(db, r)]


def find_missed_time_out(db: Session, employee_id: int | None):
    """The oldest day this employee still has to file a time out for."""
    if not employee_id:
        return None
    records = open_missed_records(db, employee_id)
    return records[0] if records else None


def missed_payload(record) -> dict | None:
    if not record:
        return None
    return {
        "attendance_id": record.id,
        "attendance_date": str(record.attendance_date),
        "date_label": record.attendance_date.strftime("%a, %b %d"),
        "time_in": format_attendance_time_only(record.check_in_time),
    }


def ensure_no_missed_time_out(db: Session, employee_id: int | None):
    record = find_missed_time_out(db, employee_id)
    if record:
        raise HTTPException(
            status_code=409,
            detail=(
                f"You didn't time out on {record.attendance_date:%a, %b %d}. "
                "Enter your time out for that day first."
            ),
        )


def _missed_time_utc(record, hhmm: str) -> datetime:
    """"18:30" on the record's day (PH) -> naive UTC. Earlier than the
    time in = the next morning (a night shift). Can't be in the future."""
    try:
        clock = datetime.strptime((hhmm or "").strip(), "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Enter the time out as HH:MM (24-hour).")
    local = PH_TZ.localize(datetime.combine(record.attendance_date, clock))
    check_in = record.check_in_time
    if check_in is not None:
        check_in_utc = check_in if check_in.tzinfo else UTC.localize(check_in)
        if local <= check_in_utc:
            local = PH_TZ.localize(
                datetime.combine(record.attendance_date + timedelta(days=1), clock)
            )
    out_utc = local.astimezone(UTC)
    if out_utc > datetime.now(UTC):
        raise HTTPException(status_code=400, detail="The time out can't be in the future.")
    return out_utc.replace(tzinfo=None)


def file_missed_time_out(db: Session, record, hhmm: str, reason: str, user: User | None):
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Say why you didn't time out.")
    if record.check_out_time is not None or record.missed_out_filed_at is not None:
        raise HTTPException(status_code=400, detail="That day's time out is already in.")
    ensure_unlocked(db, record.employee_id, record.attendance_date, "attendance")
    requested = _missed_time_utc(record, hhmm)
    record.missed_out_requested_at = requested
    record.missed_out_reason = reason[:1000]
    record.missed_out_filed_at = datetime.utcnow()
    record.time_out_face_review_status = "MISSED_TIME_OUT"
    record.time_out_face_review_reason = (
        f"Forgot to time out -- says they left at "
        f"{format_attendance_time_only(requested)}: {reason}"
    )[:1000]
    if user is not None:
        record.time_out_review_log = append_log(
            record.time_out_review_log, user, "filed", f"Left at {format_attendance_time_only(requested)}: {reason}"
        )
    start_attendance_review(db, record, "time_out")


def start_attendance_review(db: Session, record, side: str):
    """If this side needs review, work out who approves it from the Org
    Chart (heads with Attendance ticked, layer by layer). No chain =
    only superadmin / an Attendance grid "Can edit" grant, as before."""
    if getattr(record, f"{side}_face_review_status") not in REVIEW_PENDING_STATUSES:
        return
    employee = record.employee or (
        db.query(Employee).filter(Employee.id == record.employee_id).first()
    )
    user = db.query(User).filter(User.employee_id == record.employee_id).first()
    chain = resolve_chain(db, employee, user, "attendance")
    setattr(record, f"{side}_review_chain", dump_chain(chain))
    setattr(record, f"{side}_review_step", 0)


WORK_PROOF_MAX_BYTES = 50 * 1024 * 1024
NO_PROOF_NOTE = "No work photo/video uploaded."


def work_report_head(db: Session, employee_id: int | None, user: User | None) -> int | None:
    """The immediate head who checks this person's work accomplished --
    the first head above them whose Org Chart unit ticks "Work
    accomplished". None = they don't need to report it."""
    if not employee_id:
        return None
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    chain = resolve_chain(db, employee, user, "work_report")
    return chain[0] if chain else None


def check_work_report(db: Session, record, employee_id: int, user, work_accomplished, proof):
    """Validates and saves the work accomplished typed at time out.
    Returns (head_id, proof or None, missing_proof). Text is required
    when their head checks work; the photo/video proof is optional."""
    head_id = work_report_head(db, employee_id, user)
    text = (work_accomplished or "").strip()
    if head_id and not text:
        raise HTTPException(
            status_code=400, detail="Please write what you worked on today."
        )
    record.work_accomplished = text[:2000] or None
    if proof is not None and not (proof.filename or "").strip():
        proof = None
    if proof is not None:
        kind = (proof.content_type or "").split("/")[0]
        if kind not in ("image", "video"):
            raise HTTPException(
                status_code=400, detail="Work proof must be a photo or a video."
            )
        proof.file.seek(0, 2)
        size = proof.file.tell()
        proof.file.seek(0)
        if size > WORK_PROOF_MAX_BYTES:
            raise HTTPException(
                status_code=400,
                detail="The video is too large (50 MB max). Record a shorter one.",
            )
    missing = bool(head_id) and proof is None
    record.work_proof_missing = missing if head_id else None
    return head_id, proof, missing


def review_time_out(db: Session, record, head_id, missing_proof: bool):
    """Starts the time-out review. A missing work proof sends it to the
    immediate head who checks work -- unless something else (outside
    the work area, face check) already needs the attendance approvers."""
    already_flagged = record.time_out_face_review_status in REVIEW_PENDING_STATUSES
    if missing_proof:
        reason = record.time_out_face_review_reason
        record.time_out_face_review_status = "NEEDS_REVIEW"
        record.time_out_face_review_reason = (
            f"{reason} {NO_PROOF_NOTE}".strip() if reason else NO_PROOF_NOTE
        )
    start_attendance_review(db, record, "time_out")
    if missing_proof and (not already_flagged or not record.time_out_review_chain):
        record.time_out_review_chain = dump_chain([head_id])
        record.time_out_review_step = 0


def save_work_proof(db: Session, file_service, record, proof, label, lat, lng, uploader_id):
    if proof is None:
        return
    db.add(
        FileModel(
            entity_type="attendance",
            entity_id=record.id,
            document_type="WORK_PROOF",
            file_url=file_service.upload(
                _watermark_timestamp(proof, label, lat, lng),
                f"attendance/{record.id}/work-proof",
            ),
            uploaded_by=uploader_id,
        )
    )


def _ph_stamp(value) -> str | None:
    """A stored (UTC) time as PH "YYYY-MM-DD 08:05 AM", for the log."""
    if not value:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return (value + timedelta(hours=8)).strftime("%Y-%m-%d %I:%M %p")


def log_adjustment(db: Session, record, field: str, old, new, user, reason=None):
    """One line of the attendance audit trail (AttendanceAdjustment)."""
    if old == new:
        return
    db.add(
        AttendanceAdjustment(
            attendance_id=record.id,
            field=field,
            old_value=None if old is None else str(old)[:255],
            new_value=None if new is None else str(new)[:255],
            reason=(reason or "").strip() or None,
            changed_by_user_id=user.id if user else None,
        )
    )


def ensure_in_team(db: Session, user, employee_id: int):
    """Org chart heads only act on their own people (team_scope)."""
    scope = team_scope(db, user)
    if scope is not None and employee_id not in scope["employee_ids"]:
        raise HTTPException(
            status_code=403,
            detail="This employee isn't in your team on the Org Chart.",
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
    remarks: str | None,
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
        remarks=remarks,
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
    require_role_or_module(
        roles=["admin", "superadmin", "motorpool"], module_key="hris.attendance"
    )(current_user=current_user, db=db)

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
    # Forgot to time out on an earlier day: file that first.
    ensure_no_missed_time_out(db, employee_id)

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

    outside, geofence_note, photo_label = check_attendance_geofence(
        latitude, longitude
    )
    flag_side_for_geofence(record, "time_in", outside, geofence_note)
    start_attendance_review(db, record, "time_in")

    if not existing:
        db.add(record)
        db.flush()

    file_service = FileService()
    photo_url = file_service.upload(
        _watermark_timestamp(photo, photo_label, latitude, longitude),
        f"attendance/{record.id}/time-in",
    )

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


@router.post("/time-out-selfie", response_model=AttendanceResponse)
def time_out_selfie(
    latitude: float = Form(...),
    longitude: float = Form(...),
    address: str = Form(...),
    photo: UploadFile = File(...),
    # Work accomplished (required when their head's unit ticks "Work
    # accomplished") and its photo/video proof (optional -- leaving it
    # out sends this time out to that head for review).
    work_accomplished: str | None = Form(None),
    proof: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mobile selfie time-out -- the counterpart of time_in_selfie():
    same access, geofence flag (outside = accepted but sent to review)
    and GPS/time watermark on the photo."""
    require_role_or_module(
        roles=["admin", "superadmin", "motorpool"], module_key="hris.attendance"
    )(current_user=current_user, db=db)

    employee_id = current_user.employee_id
    if not employee_id:
        raise HTTPException(
            status_code=400,
            detail="User account is not linked to an employee.",
        )

    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Photo must be an image file")

    today = datetime.now(ZoneInfo("Asia/Manila")).date()
    record = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.attendance_date == today,
        )
        .first()
    )

    if not record or not record.check_in_time:
        raise HTTPException(status_code=400, detail="You haven't timed in today.")
    if record.check_out_time:
        raise HTTPException(status_code=400, detail="You already timed out today.")

    record.check_out_time = datetime.utcnow()
    record.time_out_latitude = latitude
    record.time_out_longitude = longitude
    record.time_out_address = address

    outside, geofence_note, photo_label = check_attendance_geofence(
        latitude, longitude
    )
    flag_side_for_geofence(record, "time_out", outside, geofence_note)

    # Work accomplished (asked when their head's Org Chart unit ticks it).
    head_id, proof, missing_proof = check_work_report(
        db, record, employee_id, current_user, work_accomplished, proof
    )
    review_time_out(db, record, head_id, missing_proof)

    file_service = FileService()
    photo_url = file_service.upload(
        _watermark_timestamp(photo, photo_label, latitude, longitude),
        f"attendance/{record.id}/time-out",
    )
    save_work_proof(
        db, file_service, record, proof, photo_label, latitude, longitude, current_user.id
    )

    db.add(
        FileModel(
            entity_type="attendance",
            entity_id=record.id,
            document_type="ATTENDANCE_TIME_OUT",
            file_url=photo_url,
            uploaded_by=current_user.id,
        )
    )

    db.commit()
    db.refresh(record)

    time_in_photo = (
        db.query(FileModel.file_url)
        .filter(
            FileModel.entity_type == "attendance",
            FileModel.entity_id == record.id,
            FileModel.document_type == "ATTENDANCE_TIME_IN",
        )
        .scalar()
    )
    record.time_in_photo_url = time_in_photo
    record.time_out_photo_url = photo_url

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
        trip_date = utc_to_ph_date(trip.start_time)

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

    # Whether time out asks for work accomplished + photo/video.
    head_id = work_report_head(db, current_user.employee_id, current_user)
    head = db.query(User).filter(User.id == head_id).first() if head_id else None
    work_report = {
        "work_report_required": bool(head_id),
        "work_report_head": display_name(head) if head else None,
    }

    # Forgot to time out on an earlier day -> asked before time in.
    work_report["missed_time_out"] = missed_payload(
        find_missed_time_out(db, current_user.employee_id)
    )

    if not record:
        return {
            "has_record": False,
            "check_in_time": None,
            "check_out_time": None,
            "status": None,
            **work_report,
        }

    return {
        **work_report,
        "work_accomplished": record.work_accomplished,
        "has_record": True,
        "id": record.id,
        "attendance_date": str(record.attendance_date),
        "check_in_time": format_attendance_time_only(record.check_in_time),
        "check_out_time": format_attendance_time_only(record.check_out_time),
        "status": record.status,
        "time_in_latitude": record.time_in_latitude,
        "time_in_longitude": record.time_in_longitude,
        "time_in_address": record.time_in_address,
        "time_in_outside_geofence": record.time_in_outside_geofence,
        "time_out_outside_geofence": record.time_out_outside_geofence,
    }


@router.get("/my-history")
def get_my_attendance_history(
    month: str | None = None,
    limit: int = 60,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attendance history for the logged-in user's own employee record.

    `month` is an optional "YYYY-MM" filter; defaults to the current
    PH-timezone month when omitted.
    """
    if not current_user.employee_id:
        raise HTTPException(
            status_code=400,
            detail="User account is not linked to an employee.",
        )

    if month:
        try:
            year_str, month_str = month.split("-")
            period_start = date(int(year_str), int(month_str), 1)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid month format, expected YYYY-MM.")
    else:
        period_start = datetime.now(ZoneInfo("Asia/Manila")).date().replace(day=1)

    if period_start.month == 12:
        period_end = date(period_start.year + 1, 1, 1)
    else:
        period_end = date(period_start.year, period_start.month + 1, 1)

    records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == current_user.employee_id,
            AttendanceRecord.attendance_date >= period_start,
            AttendanceRecord.attendance_date < period_end,
        )
        .order_by(AttendanceRecord.attendance_date.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": record.id,
            "attendance_date": str(record.attendance_date),
            "check_in_time": format_attendance_time_only(record.check_in_time),
            "check_out_time": format_attendance_time_only(record.check_out_time),
            "status": record.status,
            "remarks": record.remarks,
        }
        for record in records
    ]


@router.post("/", response_model=AttendanceResponse)
def mark_attendance(
    attendance_in: AttendanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Entering attendance by hand: same people who can edit it.
    if not has_editable_grant(
        db, current_user, ["hris.attendance_list_view", "hris.attendance_grid_view"]
    ):
        raise HTTPException(
            status_code=403,
            detail="You don't have edit access to attendance records.",
        )

    employee = db.query(Employee).filter_by(id=attendance_in.employee_id).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    ensure_in_team(db, current_user, employee.id)
    ensure_unlocked(db, employee.id, attendance_in.attendance_date, "attendance")

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
        remarks=attendance_in.remarks,
        user_id=current_user.id,
        attendance_date=attendance_in.attendance_date,
    )

    if not record:
        raise HTTPException(
            status_code=400,
            detail="Attendance already recorded for this date.",
        )

    db.flush()
    log_adjustment(
        db, record, "created", None, f"Entered manually ({attendance_in.status})", current_user
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
            remarks=getattr(att, "remarks", None),
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
    department: str | None = None,
    attendance_date: date | None = None,
    # Callers that don't render photos (e.g. PayrollList, which only
    # needs hours/status/trip data) can skip these two batch queries and
    # the profile/time-in/time-out URL fields entirely by passing false.
    include_photos: bool = True,
    # "all" = everyone, for the Payroll page -- only honoured for people
    # with payroll access; an org chart head otherwise sees their team.
    scope: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sync_trip_attendance_records(db, current_user.id)

    team = (
        None
        if scope == "all" and can_view_all_payroll(db, current_user)
        else team_scope(db, current_user)
    )

    # ---------------------------------------
    # ATTENDANCE QUERY
    # ---------------------------------------

    query = (
        db.query(AttendanceRecord)
        .join(Employee, Employee.id == AttendanceRecord.employee_id)
    )

    if department and department.lower() != "all":
        query = query.filter(Employee.department == department)

    if attendance_date:
        query = query.filter(
            AttendanceRecord.attendance_date == attendance_date
        )

    if team is not None:
        query = query.filter(
            AttendanceRecord.employee_id.in_(team["employee_ids"] or [0])
        )

    records = (
        query
        .order_by(AttendanceRecord.attendance_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    # ---------------------------------------
    # ACTIVE EMPLOYEE COUNT
    # ADMIN + motorpool
    #
    # This count is independent of:
    # - selected attendance date
    # - attendance department filter
    # ---------------------------------------

    admin_count = (
        db.query(func.count(Employee.id))
        .filter(
            Employee.is_active == 1,
            Employee.department == "Admin",
        )
        .scalar()
        or 0
    )

    motorpool_count = (
        db.query(func.count(Employee.id))
        .filter(
            Employee.is_active == 1,
            Employee.department == "Motorpool",
        )
        .scalar()
        or 0
    )

    active_employee_count = admin_count + motorpool_count

    # ---------------------------------------
    # DEBUG LOG
    # ---------------------------------------

    print("========================================")
    print("ACTIVE EMPLOYEE COUNT")
    print(f"Admin: {admin_count}")
    print(f"motorpool: {motorpool_count}")
    print(f"Total Admin + motorpool: {active_employee_count}")
    print("========================================")

    # ---------------------------------------
    # EMPLOYEE DATA
    # ---------------------------------------

    employee_ids = list({record.employee_id for record in records})

    employees = (
        db.query(Employee)
        .filter(Employee.id.in_(employee_ids))
        .all()
    )

    employee_map = {
        employee.id: employee
        for employee in employees
    }

    valid_statuses = [
        "COMPLETED",
        "completed",
        "APPROVED",
        "approved",
    ]

    # ---------------------------------------
    # BATCH LOOKUPS
    #
    # The previous version of this endpoint issued 5 extra queries PER
    # ATTENDANCE RECORD returned (profile photo, driver trips, helper
    # trips, time-in photo, time-out photo) - for a 5000-record page
    # that is up to 25,000 additional round trips, two of which also
    # ran a non-sargable date/timezone SQL function per row against the
    # trips table, forcing a full scan each time. Everything below is
    # fetched once for the whole page and matched up in memory instead,
    # which is what made this endpoint (and PayrollList, its main
    # consumer) slow to load.
    # ---------------------------------------

    record_ids = [record.id for record in records]

    # Hand-edits per record (audit trail), oldest first.
    adjustments_map: dict[int, list] = {}
    if record_ids:
        for adj in (
            db.query(AttendanceAdjustment)
            .options(joinedload(AttendanceAdjustment.changed_by).joinedload(User.employee))
            .filter(AttendanceAdjustment.attendance_id.in_(record_ids))
            .order_by(AttendanceAdjustment.changed_at.asc(), AttendanceAdjustment.id.asc())
        ):
            adjustments_map.setdefault(adj.attendance_id, []).append(
                {
                    "field": adj.field,
                    "old_value": adj.old_value,
                    "new_value": adj.new_value,
                    "reason": adj.reason,
                    "changed_by": display_name(adj.changed_by) if adj.changed_by else None,
                    "changed_at": _ph_stamp(adj.changed_at),
                }
            )

    # --- Profile photos (one lookup for every employee on the page) ---
    profile_photo_map = {}

    if include_photos and employee_ids:
        for photo in (
            db.query(FileModel)
            .filter(
                FileModel.entity_type == "employee",
                FileModel.entity_id.in_(employee_ids),
                FileModel.document_type == "PROFILE_IMAGE",
            )
            .all()
        ):
            profile_photo_map[photo.entity_id] = photo.file_url

    # --- Attendance time-in/time-out photos, keyed by record + type ---
    attendance_photo_map = {}

    if include_photos and record_ids:
        for photo in (
            db.query(FileModel)
            .filter(
                FileModel.entity_type == "attendance",
                FileModel.entity_id.in_(record_ids),
                FileModel.document_type.in_(
                    ["ATTENDANCE_TIME_IN", "ATTENDANCE_TIME_OUT", "WORK_PROOF"]
                ),
            )
            .all()
        ):
            attendance_photo_map[(photo.entity_id, photo.document_type)] = (
                photo.file_url
            )

    # --- Driver + helper trips for every employee on the page, grouped
    #     by (employee_id, Philippine attendance date) so each record
    #     below can look its trips up in memory instead of querying
    #     the trips table again. ---
    trips_by_employee_date = defaultdict(list)
    seen_trip_ids_by_key = defaultdict(set)
    rate_rules = load_rules(db)

    if employee_ids:
        driver_trips = (
            db.query(Trip, User.employee_id)
            .join(User, User.id == Trip.driver_id)
            .options(
                joinedload(Trip.vehicle_unit),
                joinedload(Trip.trip_rate_profile),
                joinedload(Trip.destination_store),
            )
            .filter(
                User.employee_id.in_(employee_ids),
                Trip.status.in_(valid_statuses),
            )
            .all()
        )

        helper_trips = (
            db.query(Trip, TripHelper.helper_id)
            .join(TripHelper, TripHelper.trip_id == Trip.id)
            .options(
                joinedload(Trip.vehicle_unit),
                joinedload(Trip.trip_rate_profile),
                joinedload(Trip.destination_store),
            )
            .filter(
                TripHelper.helper_id.in_(employee_ids),
                Trip.status.in_(valid_statuses),
            )
            .all()
        )

        for trip, trip_employee_id in driver_trips + helper_trips:
            trip_date = utc_to_ph_date(trip.start_time)

            if trip_date is None:
                continue

            key = (trip_employee_id, trip_date)

            if trip.id in seen_trip_ids_by_key[key]:
                continue

            seen_trip_ids_by_key[key].add(trip.id)
            trips_by_employee_date[key].append(trip)

    response = []

    # ---------------------------------------
    # BUILD ATTENDANCE RESPONSE
    # ---------------------------------------

    for record in records:
        employee = employee_map.get(record.employee_id)

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

        # ---------------------------------------
        # BUILD TRIP TICKETS
        # ---------------------------------------

        trip_tickets = []

        for trip in trips_by_employee_date.get(
            (record.employee_id, record.attendance_date), []
        ):
            trip_tickets.append(
                {
                    "trip_id": trip.id,
                    "ticket_no": trip.ticket_no,
                    "vehicle_unit_id": trip.vehicle_unit_id,

                    "vehicle_unit": (
                        trip.vehicle_unit.unit_code
                        if trip.vehicle_unit
                        else None
                    ),

                    "plate_number": (
                        trip.vehicle_unit.plate_number
                        if trip.vehicle_unit
                        else None
                    ),

                    "trip_rate_profile_id": trip.trip_rate_profile_id,

                    "trip_rate_profile": (
                        trip.trip_rate_profile.profile_name
                        if trip.trip_rate_profile
                        else None
                    ),

                    # Rates with truck type / lane / effective date rules
                    # applied (app/services/trip_rates.py).
                    **resolve_trip_rates(
                        trip, record.attendance_date, rate_rules
                    ),

                    "helper_count": (
                        trip.trip_rate_profile.helper_count
                        if trip.trip_rate_profile
                        else 0
                    ),

                    "status": (
                        trip.status.value
                        if hasattr(trip.status, "value")
                        else trip.status
                    ),

                    "start_time": (
                        trip.start_time.isoformat()
                        if trip.start_time
                        else None
                    ),

                    "end_time": (
                        trip.end_time.isoformat()
                        if trip.end_time
                        else None
                    ),
                }
            )

        total_count = len(trip_tickets)

        # ---------------------------------------
        # BUILD RESPONSE
        # ---------------------------------------

        response.append(
            {
                "id": record.id,
                "employee_id": record.employee_id,
                "employee_name": employee_name,
                "employee_department": employee_department,
                "department": employee_department,

                "profile_photo_url": profile_photo_map.get(record.employee_id),

                "attendance_date": (
                    str(record.attendance_date)
                    if record.attendance_date
                    else None
                ),

                "check_in_time": format_attendance_time_only(
                    record.check_in_time
                ),

                "check_out_time": format_attendance_time_only(
                    record.check_out_time
                ),

                "check_in_time_raw": (
                    record.check_in_time.isoformat()
                    if record.check_in_time
                    else None
                ),

                "check_out_time_raw": (
                    record.check_out_time.isoformat()
                    if record.check_out_time
                    else None
                ),

                "time_in_latitude": record.time_in_latitude,
                "time_in_longitude": record.time_in_longitude,
                "time_in_address": record.time_in_address,

                "time_out_latitude": record.time_out_latitude,
                "time_out_longitude": record.time_out_longitude,
                "time_out_address": record.time_out_address,

                "time_in_photo_url": attendance_photo_map.get(
                    (record.id, "ATTENDANCE_TIME_IN")
                ),

                "time_out_photo_url": attendance_photo_map.get(
                    (record.id, "ATTENDANCE_TIME_OUT")
                ),

                "work_accomplished": record.work_accomplished,
                "work_proof_missing": record.work_proof_missing,
                "work_proof_url": attendance_photo_map.get(
                    (record.id, "WORK_PROOF")
                ),

                "time_in_face_match_score": record.time_in_face_match_score,
                "time_in_face_review_status": record.time_in_face_review_status,
                "time_in_face_review_reason": record.time_in_face_review_reason,
                "time_in_face_checked_at": record.time_in_face_checked_at,

                "time_out_face_match_score": record.time_out_face_match_score,
                "time_out_face_review_status": record.time_out_face_review_status,
                "time_out_face_review_reason": record.time_out_face_review_reason,
                "time_out_face_checked_at": record.time_out_face_checked_at,

                "time_in_outside_geofence": record.time_in_outside_geofence,
                "time_in_geofence_note": record.time_in_geofence_note,
                "time_out_outside_geofence": record.time_out_outside_geofence,
                "time_out_geofence_note": record.time_out_geofence_note,
                "time_in_review": (
                    describe_chain(
                        db,
                        record.time_in_review_chain,
                        record.time_in_review_step,
                        record.time_in_review_log,
                        record.time_in_face_review_status
                        not in REVIEW_PENDING_STATUSES,
                    )
                    if record.time_in_review_chain
                    else None
                ),
                "time_out_review": (
                    describe_chain(
                        db,
                        record.time_out_review_chain,
                        record.time_out_review_step,
                        record.time_out_review_log,
                        record.time_out_face_review_status
                        not in REVIEW_PENDING_STATUSES,
                    )
                    if record.time_out_review_chain
                    else None
                ),

                # Kept for any caller still reading the old singular
                # fields -- mirrors time-in, which is what these always
                # represented before time-out got its own review.
                "face_match_score": record.time_in_face_match_score,
                "face_review_status": record.time_in_face_review_status,
                "face_review_reason": record.time_in_face_review_reason,
                "face_checked_at": record.time_in_face_checked_at,
                "reviewed_by_user_id": record.reviewed_by_user_id,
                "reviewed_at": record.reviewed_at,
                "attendance_method": record.attendance_method,
                "status": record.status,
                "remarks": record.remarks,
                "created_by_user_id": record.created_by_user_id,
                # Audit trail of hand-edits (empty when never adjusted).
                "adjustments": adjustments_map.get(record.id, []),

                "completed_trips": total_count,
                "trip_tickets": trip_tickets,
            }
        )

    # ---------------------------------------
    # RETURN ATTENDANCE + EMPLOYEE COUNTS
    # ---------------------------------------

    return {
        "records": response,
        "admin_count": admin_count,
        "motorpool_count": motorpool_count,
        "active_employee_count": active_employee_count,
        # Set when the viewer is an org chart head: only these employees
        # (their team) are included / should be shown.
        "team_employee_ids": sorted(team["employee_ids"]) if team else None,
        "team_units": team["unit_names"] if team else None,
    }


@router.patch("/update", response_model=AttendanceResponse)
def update_attendance(
    attendance_in: AttendanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = datetime.now(ZoneInfo("Asia/Manila")).date()

    # Superadmin, or someone granted an Attendance view with "Can edit:
    # Yes" (Org Chart -> What they can access).
    if not has_editable_grant(db, current_user, ["hris.attendance_list_view", "hris.attendance_grid_view"]):
        raise HTTPException(
            status_code=403,
            detail="You don't have edit access to attendance records.",
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
    ensure_in_team(db, current_user, record.employee_id)
    ensure_unlocked(db, record.employee_id, record.attendance_date, "attendance")

    if (
        record.status == attendance_in.status
        and record.remarks == attendance_in.remarks
    ):
        raise HTTPException(
            status_code=400,
            detail="Attendance status and remarks are already the same.",
        )

    log_adjustment(db, record, "status", record.status, attendance_in.status, current_user, attendance_in.reason)
    log_adjustment(db, record, "remarks", record.remarks, attendance_in.remarks, current_user, attendance_in.reason)
    record.status = attendance_in.status
    record.remarks = attendance_in.remarks

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
            "missed_time_out": missed_payload(find_missed_time_out(db, employee.id)),
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

    kiosk_user = db.query(User).filter(User.employee_id == employee.id).first()
    head_id = work_report_head(db, employee.id, kiosk_user)
    head = db.query(User).filter(User.id == head_id).first() if head_id else None

    return {
        "employee_id": employee.id,
        "employee_name": employee_name,
        # Time out asks for work accomplished + photo/video (Org Chart).
        "work_report_required": bool(head_id),
        "work_report_head": display_name(head) if head else None,
        "has_record": True,
        "has_timed_in": has_timed_in,
        "has_timed_out": has_timed_out,
        "time_in": format_attendance_time_only(record.check_in_time),
        "time_out": format_attendance_time_only(record.check_out_time),
        "next_action": next_action,
        "message": message,
        "missed_time_out": (
            missed_payload(find_missed_time_out(db, employee.id))
            if next_action == "time_in"
            else None
        ),
    }


@router.post("/kiosk/selfie")
def kiosk_selfie_attendance(
    employee_id: int = Form(...),
    action: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    address: str = Form(...),
    photo: UploadFile = File(...),
    # Time out only: work accomplished + optional photo/video proof.
    work_accomplished: str | None = Form(None),
    proof: UploadFile | None = File(None),
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

    # Outside the allowed area is still accepted -- it's flagged for
    # review below instead of refused.
    outside_geofence, geofence_note, photo_label = check_attendance_geofence(
        latitude, longitude
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
        ensure_no_missed_time_out(db, employee_id)

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
        kiosk_user = db.query(User).filter(User.employee_id == employee_id).first()
        head_id, proof, missing_proof = check_work_report(
            db, record, employee_id, kiosk_user, work_accomplished, proof
        )

        document_type = "ATTENDANCE_TIME_OUT"
        upload_folder = f"attendance/{record.id}/time-out"

    file_service = FileService()
    # GPS time + location burned onto the selfie, same as driver photos.
    photo_url = file_service.upload(
        _watermark_timestamp(photo, photo_label, latitude, longitude),
        upload_folder,
    )

    # Face verification runs for both time-in and time-out now -- each
    # writes to its own time_in_/time_out_ prefixed fields (see the
    # AttendanceRecord model) so a review decision on one side never
    # overwrites the other's.
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

    if action == "time_in":
        record.time_in_face_match_score = face_result["score"]
        record.time_in_face_review_status = face_result["status"]
        record.time_in_face_review_reason = face_result["reason"]
        record.time_in_face_checked_at = face_result["checked_at"]
    else:
        record.time_out_face_match_score = face_result["score"]
        record.time_out_face_review_status = face_result["status"]
        record.time_out_face_review_reason = face_result["reason"]
        record.time_out_face_checked_at = face_result["checked_at"]

    flag_side_for_geofence(record, action, outside_geofence, geofence_note)
    if action == "time_out":
        review_time_out(db, record, head_id, missing_proof)
        save_work_proof(
            db, file_service, record, proof, photo_label, latitude, longitude, None
        )
    else:
        start_attendance_review(db, record, action)

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

    done = "Time in successful." if action == "time_in" else "Time out successful."
    return {
        "message": (
            f"{done} You are outside the allowed attendance area, so this "
            "was flagged for review."
            if outside_geofence
            else done
        ),
        "outside_geofence": outside_geofence,
        "geofence_note": geofence_note,
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
        "face_match_score": face_result["score"],
        "face_review_status": face_result["status"],
        "face_review_reason": face_result["reason"],
    }


# =========================
# BELL: time in/out outside the geofence, still waiting for review
#
# For the people who can approve/reject them: superadmin, or the
# Attendance grid view granted with "Can edit: Yes". Last 7 days; a
# side drops off once it's approved or rejected.
# =========================
GEOFENCE_PENDING_STATUSES = REVIEW_PENDING_STATUSES


@router.get("/geofence-alerts")
def get_geofence_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Superadmin / Attendance grid "Can edit" grant: every one. An org
    # chart head: only the ones whose turn is with them.
    sees_all = has_editable_grant(db, current_user, ["hris.attendance_grid_view"])
    team = team_scope(db, current_user)
    since = datetime.now(ZoneInfo("Asia/Manila")).date() - timedelta(days=6)
    records = (
        db.query(AttendanceRecord)
        .options(joinedload(AttendanceRecord.employee))
        .filter(
            AttendanceRecord.attendance_date >= since,
            or_(
                and_(
                    AttendanceRecord.time_in_outside_geofence.is_(True),
                    AttendanceRecord.time_in_face_review_status.in_(
                        GEOFENCE_PENDING_STATUSES
                    ),
                ),
                and_(
                    or_(
                        AttendanceRecord.time_out_outside_geofence.is_(True),
                        AttendanceRecord.work_proof_missing.is_(True),
                    ),
                    AttendanceRecord.time_out_face_review_status.in_(
                        GEOFENCE_PENDING_STATUSES
                    ),
                ),
            ),
        )
        .all()
    )

    alerts = []
    for record in records:
        employee = record.employee
        name = (
            f"{employee.first_name} {employee.last_name}"
            if employee
            else f"Employee #{record.employee_id}"
        )
        for side, label, when in (
            ("time_in", "Time In", record.check_in_time),
            ("time_out", "Time Out", record.check_out_time),
        ):
            no_proof = side == "time_out" and bool(record.work_proof_missing)
            if (
                (getattr(record, f"{side}_outside_geofence") or no_proof)
                and getattr(record, f"{side}_face_review_status")
                in GEOFENCE_PENDING_STATUSES
                and (sees_all or _current_approver(db, record, side) == current_user.id)
                and (team is None or record.employee_id in team["employee_ids"])
            ):
                alerts.append(
                    {
                        "key": f"{record.id}-{side}",
                        "attendance_id": record.id,
                        "employee_name": name,
                        "side": side,
                        "side_label": label,
                        "attendance_date": str(record.attendance_date),
                        "time": format_attendance_time_only(when),
                        "note": " ".join(
                            n
                            for n in (
                                getattr(record, f"{side}_geofence_note"),
                                NO_PROOF_NOTE if no_proof else None,
                            )
                            if n
                        ),
                        "_sort": when or datetime.min,
                    }
                )
    alerts.sort(key=lambda a: a["_sort"], reverse=True)
    for a in alerts:
        a.pop("_sort")
    return alerts


def _current_approver(db: Session, record, side: str) -> int | None:
    """Whose turn it really is today -- an approver who's absent / on
    leave today is skipped to the next head up."""
    chain = [int(i) for i in load_json_list(getattr(record, f"{side}_review_chain"))]
    if not chain:
        return None
    index, _ = effective_step(db, chain, getattr(record, f"{side}_review_step") or 0)
    return chain[index] if index < len(chain) else None


def _get_review_record(db: Session, attendance_id: int, side: str, current_user: User):
    """The record, plus whether the caller is the org chart head whose
    turn it is (vs. a superadmin / Attendance grid "Can edit" grant,
    who can approve or reject at any point)."""
    attendance = (
        db.query(AttendanceRecord).filter(AttendanceRecord.id == attendance_id).first()
    )
    if not attendance:
        raise HTTPException(status_code=404, detail="Attendance record not found.")
    ensure_in_team(db, current_user, attendance.employee_id)
    is_turn = (
        getattr(attendance, f"{side}_face_review_status") in REVIEW_PENDING_STATUSES
        and _current_approver(db, attendance, side) == current_user.id
    )
    if not is_turn and not has_editable_grant(
        db, current_user, ["hris.attendance_grid_view"]
    ):
        raise HTTPException(
            status_code=403, detail="You can't review this attendance."
        )
    return attendance, is_turn


@router.post("/{attendance_id}/approve")
def approve_attendance(
    attendance_id: int,
    side: str = Query("time_in", pattern="^(time_in|time_out)$"),
    # Required when passing it up to the next head (what they checked).
    remarks: str | None = Body(None, embed=True),
    # Missed time out: the approver may correct the time ("HH:MM").
    time_out: str | None = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attendance, is_turn = _get_review_record(db, attendance_id, side, current_user)
    missed = side == "time_out" and attendance.time_out_face_review_status == "MISSED_TIME_OUT"
    if missed and time_out:
        attendance.missed_out_requested_at = _missed_time_utc(attendance, time_out)
    ensure_unlocked(db, attendance.employee_id, attendance.attendance_date, "attendance")

    if getattr(attendance, f"{side}_face_review_status") not in REVIEW_PENDING_STATUSES:
        raise HTTPException(status_code=400, detail="This attendance isn't waiting for review.")

    # Org chart chain: the head whose turn it is (approvers out today are
    # skipped) passes it up to the next head; the last one (or a
    # superadmin) finishes it.
    chain = [int(i) for i in load_json_list(getattr(attendance, f"{side}_review_chain"))]
    step = getattr(attendance, f"{side}_review_step") or 0
    acting, skipped = acting_index(db, chain, step, current_user.id) if chain else (None, [])
    passes_up = is_turn and acting is not None and acting < len(chain) - 1

    # A head (not superadmin) approving their own team's attendance from
    # the review grid, when it isn't their chain turn: it still goes up to
    # the heads above them (Attendance ticked) for the final approval,
    # instead of being final -- unless there's no one above.
    is_superadmin = (getattr(current_user.role, "value", current_user.role) or "") == "superadmin"
    if not is_turn and not is_superadmin and _team_scope(db, current_user) is not None:
        already = any(
            entry.get("user_id") == current_user.id and entry.get("action") == "approved"
            for entry in load_json_list(getattr(attendance, f"{side}_review_log"))
        )
        if already:
            raise HTTPException(
                status_code=400,
                detail="You already approved this -- it's waiting for the next head.",
            )
        approver_employee = (
            db.query(Employee).filter(Employee.id == current_user.employee_id).first()
            if current_user.employee_id
            else None
        )
        upper = resolve_chain(db, approver_employee, current_user, "attendance")
        if upper:
            # Record their approval as the first step, then the heads above.
            chain = [current_user.id] + [uid for uid in upper if uid != current_user.id]
            step, skipped, acting = 0, [], 0
            passes_up = True
    if passes_up and not (remarks or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Add remarks for the next approver (what you checked).",
        )
    log = log_skipped(db, getattr(attendance, f"{side}_review_log"), chain, skipped)
    setattr(
        attendance,
        f"{side}_review_log",
        append_log(log, current_user, "approved", (remarks or "").strip() or None),
    )

    message = "Attendance approved."
    if passes_up:
        setattr(attendance, f"{side}_review_chain", dump_chain(chain))
        setattr(attendance, f"{side}_review_step", acting + 1)
        # Keep it waiting for review (a face-check status stays as is).
        if getattr(attendance, f"{side}_face_review_status") not in REVIEW_PENDING_STATUSES:
            setattr(attendance, f"{side}_face_review_status", "NEEDS_REVIEW")
        next_user = db.get(User, chain[acting + 1])
        message = (
            f"Approved -- passed to {display_name(next_user) if next_user else 'the next head'}"
            " for the final approval."
        )
    else:
        if acting is not None:
            setattr(attendance, f"{side}_review_step", acting)
        setattr(attendance, f"{side}_face_review_status", "APPROVED")
        if missed and attendance.missed_out_requested_at:
            log_adjustment(
                db,
                attendance,
                "check_out_time",
                None,
                _ph_stamp(attendance.missed_out_requested_at),
                current_user,
                f"Missed time out approved: {attendance.missed_out_reason or ''}".strip(),
            )
            attendance.check_out_time = attendance.missed_out_requested_at
            message = "Time out approved and saved."

    db.commit()
    db.refresh(attendance)

    return {
        "message": message,
        "attendance_id": attendance.id,
        "side": side,
        "status": getattr(attendance, f"{side}_face_review_status"),
    }


@router.post("/{attendance_id}/reject")
def reject_attendance(
    attendance_id: int,
    side: str = Query("time_in", pattern="^(time_in|time_out)$"),
    remarks: str | None = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attendance, _ = _get_review_record(db, attendance_id, side, current_user)
    ensure_unlocked(db, attendance.employee_id, attendance.attendance_date, "attendance")

    setattr(
        attendance,
        f"{side}_review_log",
        append_log(
            getattr(attendance, f"{side}_review_log"),
            current_user,
            "rejected",
            (remarks or "").strip() or None,
        ),
    )
    setattr(attendance, f"{side}_face_review_status", "REJECTED")

    db.commit()
    db.refresh(attendance)

    return {
        "message": "Attendance rejected.",
        "attendance_id": attendance.id,
        "side": side,
        "status": getattr(attendance, f"{side}_face_review_status"),
    }


@router.post("/{attendance_id}/rotate-photo")
def rotate_attendance_photo(
    attendance_id: int,
    side: str = Query("time_in", pattern="^(time_in|time_out)$"),
    degrees: int = Body(90, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Turn a sideways selfie upright (same people who can review it).
    Saved as a new file -- the original is kept -- then the face match
    is re-run so the score reflects the upright photo."""
    attendance, _ = _get_review_record(db, attendance_id, side, current_user)
    photo = (
        db.query(FileModel)
        .filter(
            FileModel.entity_type == "attendance",
            FileModel.entity_id == attendance.id,
            FileModel.document_type == PHOTO_SIDES[side],
        )
        .order_by(FileModel.id.desc())
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="This side has no photo.")
    try:
        photo.file_url = rotate_stored_photo(photo.file_url, degrees)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=400, detail=str(error))
    rescore_side(db, attendance, side, photo.file_url)
    db.commit()
    return {
        "photo_url": photo.file_url,
        "review_status": getattr(attendance, f"{side}_face_review_status"),
        "review_reason": getattr(attendance, f"{side}_face_review_reason"),
        "face_match_score": getattr(attendance, f"{side}_face_match_score"),
    }


def _can_set_missed(db: Session, user: User, record) -> bool:
    """Superadmin / Attendance grid "Can edit", or one of the employee's
    Org Chart attendance approvers."""
    if has_editable_grant(db, user, ["hris.attendance_grid_view"]):
        return True
    employee = record.employee or db.get(Employee, record.employee_id)
    owner = db.query(User).filter(User.employee_id == record.employee_id).first()
    return user.id in resolve_chain(db, employee, owner, "attendance")


@router.post("/{attendance_id}/set-missed-time-out")
def set_missed_time_out(
    attendance_id: int,
    time_out: str = Body(..., embed=True),
    remarks: str | None = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A head enters the time out for a day their person forgot (before
    the person files it) -- saved right away."""
    record = db.query(AttendanceRecord).filter(AttendanceRecord.id == attendance_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found.")
    if not _can_set_missed(db, current_user, record):
        raise HTTPException(status_code=403, detail="You can't set this time out.")
    if record.check_out_time is not None:
        raise HTTPException(status_code=400, detail="That day already has a time out.")
    ensure_unlocked(db, record.employee_id, record.attendance_date, "attendance")
    out = _missed_time_utc(record, time_out)
    note = (remarks or "").strip() or None
    log_adjustment(
        db, record, "check_out_time", None, _ph_stamp(out), current_user,
        f"Missed time out set by head{': ' + note if note else ''}",
    )
    record.check_out_time = out
    record.missed_out_requested_at = out
    record.missed_out_filed_at = record.missed_out_filed_at or datetime.utcnow()
    record.time_out_face_review_status = "APPROVED"
    record.time_out_face_review_reason = "Forgot to time out -- set by head."
    record.time_out_review_log = append_log(
        record.time_out_review_log, current_user, "approved", note or "Set the missed time out"
    )
    db.commit()
    return {"message": "Time out saved.", "attendance_id": record.id}


class MissedTimeOutIn(BaseModel):
    attendance_id: int
    time_out: str  # "HH:MM", PH
    reason: str


@router.get("/missed-time-out")
def get_my_missed_time_out(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The earlier day I still have to enter a time out for (or null)."""
    return {"missed_time_out": missed_payload(find_missed_time_out(db, current_user.employee_id))}


@router.post("/missed-time-out")
def file_my_missed_time_out(
    payload: MissedTimeOutIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = db.query(AttendanceRecord).filter(AttendanceRecord.id == payload.attendance_id).first()
    if not record or record.employee_id != current_user.employee_id:
        raise HTTPException(status_code=404, detail="Attendance record not found.")
    file_missed_time_out(db, record, payload.time_out, payload.reason, current_user)
    db.commit()
    return {
        "message": "Sent to your head for approval.",
        "missed_time_out": missed_payload(find_missed_time_out(db, current_user.employee_id)),
    }


class KioskMissedTimeOutIn(MissedTimeOutIn):
    employee_id: int


@router.post("/kiosk/missed-time-out")
def kiosk_file_missed_time_out(
    payload: KioskMissedTimeOutIn,
    db: Session = Depends(get_db),
):
    """Kiosk version (same as kiosk time in -- by employee ID)."""
    record = db.query(AttendanceRecord).filter(AttendanceRecord.id == payload.attendance_id).first()
    if not record or record.employee_id != payload.employee_id:
        raise HTTPException(status_code=404, detail="Attendance record not found.")
    owner = db.query(User).filter(User.employee_id == payload.employee_id).first()
    file_missed_time_out(db, record, payload.time_out, payload.reason, owner)
    db.commit()
    return {
        "message": "Sent to the head for approval.",
        "missed_time_out": missed_payload(find_missed_time_out(db, payload.employee_id)),
    }


# =========================
# ATTENDANCE WAITING ON ME (org chart heads)
# =========================
@router.get("/for-my-approval")
def get_attendance_for_my_approval(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Time in/out sides waiting for review (last 30 days), newest first:
    the ones whose turn is with me on the org chart chain -- or, for a
    superadmin / Attendance grid "Can edit" grant, every pending one
    (an org chart head still only their team)."""
    since = datetime.now(ZoneInfo("Asia/Manila")).date() - timedelta(days=30)
    sees_all = has_editable_grant(db, current_user, ["hris.attendance_grid_view"])
    team = team_scope(db, current_user)
    records = (
        db.query(AttendanceRecord)
        .options(joinedload(AttendanceRecord.employee))
        .filter(
            AttendanceRecord.attendance_date >= since,
            or_(
                AttendanceRecord.time_in_face_review_status.in_(REVIEW_PENDING_STATUSES),
                AttendanceRecord.time_out_face_review_status.in_(REVIEW_PENDING_STATUSES),
            )
            if sees_all
            else or_(
                AttendanceRecord.time_in_review_chain.isnot(None),
                AttendanceRecord.time_out_review_chain.isnot(None),
            ),
        )
        .all()
    )
    if team is not None:
        records = [r for r in records if r.employee_id in team["employee_ids"]]
    photos = {
        (f.entity_id, f.document_type): f.file_url
        for f in db.query(FileModel).filter(
            FileModel.entity_type == "attendance",
            FileModel.entity_id.in_([r.id for r in records] or [0]),
        )
    }
    items = []
    for record in records:
        employee = record.employee
        for side, label, when in (
            ("time_in", "Time In", record.check_in_time),
            ("time_out", "Time Out", record.check_out_time),
        ):
            if (
                side == "time_out"
                and not record.check_out_time
                and record.time_out_face_review_status != "MISSED_TIME_OUT"
            ):
                continue
            if (
                getattr(record, f"{side}_face_review_status") in REVIEW_PENDING_STATUSES
                and (sees_all or _current_approver(db, record, side) == current_user.id)
            ):
                items.append(
                    {
                        "key": f"{record.id}-{side}",
                        "attendance_id": record.id,
                        "side": side,
                        "side_label": label,
                        "employee_name": (
                            f"{employee.first_name} {employee.last_name}"
                            if employee
                            else f"Employee #{record.employee_id}"
                        ),
                        "position": employee.position if employee else None,
                        "attendance_date": str(record.attendance_date),
                        "time": format_attendance_time_only(when),
                        "address": getattr(record, f"{side}_address"),
                        "photo_url": photos.get(
                            (record.id, f"ATTENDANCE_{side.upper()}")
                        ),
                        "outside_geofence": bool(
                            getattr(record, f"{side}_outside_geofence")
                        ),
                        "review_status": getattr(record, f"{side}_face_review_status"),
                        "review_reason": getattr(record, f"{side}_face_review_reason"),
                        **(
                            {
                                "missed_time_out": {
                                    "time_in": format_attendance_time_only(record.check_in_time),
                                    "requested_time": format_attendance_time_only(
                                        record.missed_out_requested_at
                                    ),
                                    "requested_hhmm": utc_to_ph(
                                        record.missed_out_requested_at
                                    ).strftime("%H:%M")
                                    if record.missed_out_requested_at
                                    else None,
                                    "reason": record.missed_out_reason,
                                    "filed": True,
                                }
                            }
                            if side == "time_out"
                            and record.time_out_face_review_status == "MISSED_TIME_OUT"
                            else {}
                        ),
                        **(
                            {
                                "work_accomplished": record.work_accomplished,
                                "work_proof_missing": bool(record.work_proof_missing),
                                "work_proof_url": photos.get((record.id, "WORK_PROOF")),
                            }
                            if side == "time_out"
                            else {}
                        ),
                        **describe_chain(
                            db,
                            getattr(record, f"{side}_review_chain"),
                            getattr(record, f"{side}_review_step"),
                            getattr(record, f"{side}_review_log"),
                            False,
                        ),
                        "_sort": when or datetime.min,
                    }
                )
    # Forgot to time out and hasn't filed it yet: the head can enter the
    # time out themselves.
    unfiled = open_missed_records(db)
    if team is not None:
        unfiled = [r for r in unfiled if r.employee_id in team["employee_ids"]]
    unfiled_photos = {
        f.entity_id: f.file_url
        for f in db.query(FileModel).filter(
            FileModel.entity_type == "attendance",
            FileModel.document_type == "ATTENDANCE_TIME_IN",
            FileModel.entity_id.in_([r.id for r in unfiled] or [0]),
        )
    }
    for record in unfiled:
        if not (sees_all or _can_set_missed(db, current_user, record)):
            continue
        employee = record.employee
        items.append(
            {
                "key": f"{record.id}-missed",
                "attendance_id": record.id,
                "side": "time_out",
                "side_label": "No Time Out",
                "employee_name": (
                    f"{employee.first_name} {employee.last_name}"
                    if employee
                    else f"Employee #{record.employee_id}"
                ),
                "position": employee.position if employee else None,
                "attendance_date": str(record.attendance_date),
                "time": None,
                "address": record.time_in_address,
                "photo_url": unfiled_photos.get(record.id),
                "outside_geofence": False,
                "review_status": "MISSED_TIME_OUT_UNFILED",
                "review_reason": "Forgot to time out -- not filed yet. You can enter it.",
                "missed_time_out": {
                    "time_in": format_attendance_time_only(record.check_in_time),
                    "requested_time": None,
                    "requested_hhmm": None,
                    "reason": None,
                    "filed": False,
                },
                "approval_steps": [],
                "approval_log": [],
                "_sort": record.check_in_time or datetime.min,
            }
        )

    items.sort(key=lambda i: i["_sort"], reverse=True)
    for i in items:
        i.pop("_sort")
    return items


@router.patch("/{attendance_id}/adjust-time")
def adjust_attendance_time(
    attendance_id: int,
    payload: AttendanceTimeAdjust,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_superadmin_or_editable(["hris.attendance_list_view", "hris.attendance_grid_view"])
    ),
):
    # Editing/overriding an already-recorded attendance time: superadmin,
    # or an Attendance view granted with "Can edit: Yes" (see
    # AttendanceGridReview.jsx / AttendanceTable.jsx on the frontend,
    # which hide these controls from everyone else).
    attendance = (
        db.query(AttendanceRecord).filter(AttendanceRecord.id == attendance_id).first()
    )

    if not attendance:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found.",
        )
    ensure_in_team(db, current_user, attendance.employee_id)
    ensure_unlocked(db, attendance.employee_id, attendance.attendance_date, "attendance")

    try:
        new_times = {
            field: PH_TZ.localize(
                datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            ).astimezone(UTC)
            for field, value in (
                ("check_in_time", payload.check_in_time),
                ("check_out_time", payload.check_out_time),
            )
            if value
        }
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=("Invalid datetime format. " "Use YYYY-MM-DD HH:MM:SS"),
        )

    # Every change is logged (old -> new, who, when, why). Overwriting a
    # time that was already there needs a reason.
    for field, new_value in new_times.items():
        old_stamp = _ph_stamp(getattr(attendance, field))
        new_stamp = _ph_stamp(new_value)
        if old_stamp == new_stamp:
            continue
        # A hand-entered record is auto-stamped with the time it was
        # entered; setting its real time the first time isn't a change.
        if (
            attendance.attendance_method == "MANUAL"
            and not db.query(AttendanceAdjustment.id)
            .filter(
                AttendanceAdjustment.attendance_id == attendance.id,
                AttendanceAdjustment.field == field,
            )
            .first()
        ):
            old_stamp = None
        if old_stamp and not (payload.reason or "").strip():
            raise HTTPException(
                status_code=400,
                detail="Give a reason for changing the recorded time.",
            )
        log_adjustment(
            db, attendance, field, old_stamp, new_stamp, current_user, payload.reason
        )
        setattr(attendance, field, new_value)

    db.commit()
    db.refresh(attendance)

    return {
        "message": "Attendance adjusted successfully.",
        "attendance_id": attendance.id,
        "check_in_time": attendance.check_in_time,
        "check_out_time": attendance.check_out_time,
    }
