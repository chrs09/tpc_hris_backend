"""HRIS -> Attendance Locations: where employees may time in/out from
(selfie or kiosk) and how far around it, which locations each employee
is assigned to, and the minimum hours of duty (company default + per
employee). The checks themselves run in app/api/attendance.py
(check_attendance_geofence, apply_short_duty).

Access: superadmin, or the "hris.attendance_locations" module (a
view-only grant can look but not change anything).
"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.app_setting import AppSetting
from app.models.attendance_location import AttendanceLocation
from app.models.employees import Employee
from app.models.user import User
from app.services.approval_chain import load_json_list

router = APIRouter(prefix="/attendance-locations", tags=["Attendance Locations"])

_require_access = require_role_or_module(
    roles=["superadmin"], module_key="hris.attendance_locations"
)

MIN_DUTY_SETTING = "attendance_min_duty_minutes"
MAX_RADIUS_METERS = 5000
MAX_DUTY_MINUTES = 24 * 60


class LocationIn(BaseModel):
    name: str
    latitude: float
    longitude: float
    radius_meters: int = 150
    is_active: bool = True


class LocationPatch(BaseModel):
    name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_meters: int | None = None
    is_active: bool | None = None


class MinDutyIn(BaseModel):
    min_duty_minutes: int


class EmployeeRulesIn(BaseModel):
    location_ids: list[int] = []
    # None = use the company default.
    min_duty_minutes: int | None = None


def _serialize(location: AttendanceLocation, counts: dict) -> dict:
    return {
        "id": location.id,
        "name": location.name,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "radius_meters": location.radius_meters,
        "is_active": bool(location.is_active),
        "assigned_employees": counts.get(location.id, 0),
    }


def _check_location(name, latitude, longitude, radius):
    if name is not None and not name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    if latitude is not None and not -90 <= latitude <= 90:
        raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90.")
    if longitude is not None and not -180 <= longitude <= 180:
        raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180.")
    if radius is not None and not 10 <= radius <= MAX_RADIUS_METERS:
        raise HTTPException(
            status_code=400,
            detail=f"Perimeter must be 10 to {MAX_RADIUS_METERS} meters.",
        )


def _check_minutes(minutes):
    if minutes is not None and not 0 <= minutes <= MAX_DUTY_MINUTES:
        raise HTTPException(status_code=400, detail="Minimum duty must be 0 to 24 hours.")


def _assigned_counts(db: Session) -> dict:
    counts = {}
    for (ids,) in db.query(Employee.attendance_location_ids).filter(
        Employee.is_active == 1, Employee.attendance_location_ids.isnot(None)
    ):
        for location_id in load_json_list(ids):
            counts[int(location_id)] = counts.get(int(location_id), 0) + 1
    return counts


def _company_minutes(db: Session) -> int:
    setting = db.query(AppSetting).filter(AppSetting.key == MIN_DUTY_SETTING).first()
    try:
        return int(setting.value) if setting else 0
    except ValueError:
        return 0


# ---------------- locations
@router.get("")
def list_locations(db: Session = Depends(get_db), _: User = Depends(_require_access)):
    counts = _assigned_counts(db)
    locations = db.query(AttendanceLocation).order_by(
        AttendanceLocation.is_active.desc(), AttendanceLocation.name
    )
    return [_serialize(location, counts) for location in locations]


@router.post("")
def create_location(
    payload: LocationIn, db: Session = Depends(get_db), _: User = Depends(_require_access)
):
    _check_location(payload.name, payload.latitude, payload.longitude, payload.radius_meters)
    location = AttendanceLocation(
        name=payload.name.strip(),
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_meters=payload.radius_meters,
        is_active=payload.is_active,
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return _serialize(location, {})


@router.patch("/{location_id}")
def update_location(
    location_id: int,
    payload: LocationPatch,
    db: Session = Depends(get_db),
    _: User = Depends(_require_access),
):
    location = db.get(AttendanceLocation, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found.")
    _check_location(payload.name, payload.latitude, payload.longitude, payload.radius_meters)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(location, field, value.strip() if field == "name" else value)
    location.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(location)
    return _serialize(location, _assigned_counts(db))


# ---------------- minimum hours of duty (company default)
@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(_require_access)):
    return {"min_duty_minutes": _company_minutes(db)}


@router.put("/settings")
def save_settings(
    payload: MinDutyIn, db: Session = Depends(get_db), _: User = Depends(_require_access)
):
    _check_minutes(payload.min_duty_minutes)
    setting = db.query(AppSetting).filter(AppSetting.key == MIN_DUTY_SETTING).first()
    if not setting:
        setting = AppSetting(key=MIN_DUTY_SETTING, value="0")
        db.add(setting)
    setting.value = str(payload.min_duty_minutes)
    db.commit()
    return {"min_duty_minutes": payload.min_duty_minutes}


# ---------------- per employee
@router.get("/employees")
def list_employee_rules(db: Session = Depends(get_db), _: User = Depends(_require_access)):
    employees = (
        db.query(Employee)
        .filter(Employee.is_active == 1)
        .order_by(Employee.first_name, Employee.last_name)
        .all()
    )
    return [
        {
            "id": e.id,
            "name": " ".join(filter(None, [e.first_name, e.last_name])).strip(),
            "department": e.department,
            "position": e.position,
            "location_ids": [int(i) for i in load_json_list(e.attendance_location_ids)],
            "min_duty_minutes": e.min_duty_minutes,
        }
        for e in employees
    ]


@router.put("/employees/{employee_id}")
def save_employee_rules(
    employee_id: int,
    payload: EmployeeRulesIn,
    db: Session = Depends(get_db),
    _: User = Depends(_require_access),
):
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found.")
    _check_minutes(payload.min_duty_minutes)
    ids = sorted(set(payload.location_ids))
    if ids:
        found = {
            row.id
            for row in db.query(AttendanceLocation.id).filter(AttendanceLocation.id.in_(ids))
        }
        if len(found) != len(ids):
            raise HTTPException(status_code=400, detail="Unknown attendance location.")
    employee.attendance_location_ids = json.dumps(ids) if ids else None
    employee.min_duty_minutes = payload.min_duty_minutes
    db.commit()
    return {
        "id": employee.id,
        "location_ids": ids,
        "min_duty_minutes": employee.min_duty_minutes,
    }
