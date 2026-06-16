from fastapi import APIRouter, Depends, HTTPException, Form
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.database import get_db

from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.vehicle_unit import VehicleUnit
from app.models.TripRate import TripRateProfile
from app.utils.response import api_response

router = APIRouter(
    prefix="/trip-maintenance",
    tags=["Trip Maintenance"],
)


# VEHICLE UNITS
@router.get("/vehicle-units")
def get_vehicle_units(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    units = db.query(VehicleUnit).order_by(VehicleUnit.plate_number.asc()).all()

    response = [
        {
            "id": unit.id,
            "unit_code": unit.unit_code,
            "plate_number": unit.plate_number,
            "description": unit.description,
            "is_active": unit.is_active,
        }
        for unit in units
    ]

    return api_response(response)


@router.get("/vehicle-units/active")
def get_active_vehicle_units(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    units = (
        db.query(VehicleUnit)
        .filter(VehicleUnit.is_active.is_(True), VehicleUnit.is_available.is_(True))
        .order_by(VehicleUnit.unit_code.asc())
        .all()
    )

    response = [
        {
            "id": unit.id,
            "unit_code": unit.unit_code,
            "plate_number": unit.plate_number,
            "description": unit.description,
        }
        for unit in units
    ]

    return api_response(response)


@router.post("/vehicle-units")
def create_vehicle_unit(
    unit_code: str = Form(None),
    plate_number: str = Form(...),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing_plate = (
        db.query(VehicleUnit).filter(VehicleUnit.plate_number == plate_number).first()
    )

    if existing_plate:
        raise HTTPException(
            status_code=400,
            detail="Plate number already exists",
        )

    if unit_code:
        existing_unit_code = (
            db.query(VehicleUnit).filter(VehicleUnit.unit_code == unit_code).first()
        )

        if existing_unit_code:
            raise HTTPException(
                status_code=400,
                detail="Unit code already exists",
            )

    vehicle_unit = VehicleUnit(
        unit_code=unit_code,
        plate_number=plate_number,
        description=description,
        created_by=current_user.id,
    )

    db.add(vehicle_unit)
    db.commit()
    db.refresh(vehicle_unit)

    return api_response(
        {
            "message": "Vehicle unit created successfully",
            "id": vehicle_unit.id,
        }
    )


@router.patch("/vehicle-units/{unit_id}")
def update_vehicle_unit(
    unit_id: int,
    unit_code: str = Form(None),
    plate_number: str = Form(None),
    description: str = Form(None),
    is_active: bool = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    vehicle_unit = db.query(VehicleUnit).filter(VehicleUnit.id == unit_id).first()

    if not vehicle_unit:
        raise HTTPException(
            status_code=404,
            detail="Vehicle unit not found",
        )

    if unit_code is not None:
        existing_unit_code = (
            db.query(VehicleUnit)
            .filter(
                VehicleUnit.unit_code == unit_code,
                VehicleUnit.id != unit_id,
            )
            .first()
        )

        if existing_unit_code:
            raise HTTPException(
                status_code=400,
                detail="Unit code already exists",
            )

        vehicle_unit.unit_code = unit_code

    if plate_number is not None:
        existing_plate = (
            db.query(VehicleUnit)
            .filter(
                VehicleUnit.plate_number == plate_number,
                VehicleUnit.id != unit_id,
            )
            .first()
        )

        if existing_plate:
            raise HTTPException(
                status_code=400,
                detail="Plate number already exists",
            )

        vehicle_unit.plate_number = plate_number

    if description is not None:
        vehicle_unit.description = description

    if is_active is not None:
        vehicle_unit.is_active = is_active

    vehicle_unit.updated_by = current_user.id
    vehicle_unit.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(vehicle_unit)

    return api_response({"message": "Vehicle unit updated successfully"})


@router.delete("/vehicle-units/{unit_id}")
def delete_vehicle_unit(
    unit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    vehicle_unit = db.query(VehicleUnit).filter(VehicleUnit.id == unit_id).first()

    if not vehicle_unit:
        raise HTTPException(
            status_code=404,
            detail="Vehicle unit not found",
        )

    vehicle_unit.is_active = False
    vehicle_unit.updated_by = current_user.id
    vehicle_unit.updated_at = datetime.utcnow()

    db.commit()

    return api_response({"message": "Vehicle unit deactivated"})


# TRIP PROFILE
@router.get("/rate-profiles")
def get_rate_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profiles = (
        db.query(TripRateProfile).order_by(TripRateProfile.profile_name.asc()).all()
    )

    response = [
        {
            "id": profile.id,
            "profile_name": profile.profile_name,
            "helper_count": profile.helper_count,
            "driver_first_trip_rate": float(profile.driver_first_trip_rate),
            "driver_next_trip_rate": float(profile.driver_next_trip_rate),
            "helper_first_trip_rate": float(profile.helper_first_trip_rate),
            "helper_next_trip_rate": float(profile.helper_next_trip_rate),
            "is_active": profile.is_active,
        }
        for profile in profiles
    ]

    return api_response(response)


@router.get("/rate-profiles/active")
def get_active_rate_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profiles = (
        db.query(TripRateProfile)
        .filter(TripRateProfile.is_active.is_(True))
        .order_by(TripRateProfile.profile_name.asc())
        .all()
    )

    response = [
        {
            "id": profile.id,
            "profile_name": profile.profile_name,
            "helper_count": profile.helper_count,
        }
        for profile in profiles
    ]

    return api_response(response)


@router.post("/rate-profiles")
def create_rate_profile(
    profile_name: str = Form(...),
    helper_count: int = Form(...),
    driver_first_trip_rate: float = Form(...),
    driver_next_trip_rate: float = Form(...),
    helper_first_trip_rate: float = Form(...),
    helper_next_trip_rate: float = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = (
        db.query(TripRateProfile)
        .filter(TripRateProfile.profile_name == profile_name)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Profile already exists",
        )

    profile = TripRateProfile(
        profile_name=profile_name,
        helper_count=helper_count,
        driver_first_trip_rate=driver_first_trip_rate,
        driver_next_trip_rate=driver_next_trip_rate,
        helper_first_trip_rate=helper_first_trip_rate,
        helper_next_trip_rate=helper_next_trip_rate,
        created_by=current_user.id,
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return api_response(
        {
            "message": "Rate profile created successfully",
            "id": profile.id,
        }
    )


@router.patch("/rate-profiles/{profile_id}")
def update_rate_profile(
    profile_id: int,
    profile_name: str = Form(None),
    helper_count: int = Form(None),
    driver_first_trip_rate: float = Form(None),
    driver_next_trip_rate: float = Form(None),
    helper_first_trip_rate: float = Form(None),
    helper_next_trip_rate: float = Form(None),
    is_active: bool = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = db.query(TripRateProfile).filter(TripRateProfile.id == profile_id).first()

    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Profile not found",
        )

    if profile_name is not None:
        existing = (
            db.query(TripRateProfile)
            .filter(
                TripRateProfile.profile_name == profile_name,
                TripRateProfile.id != profile_id,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Profile name already exists",
            )

        profile.profile_name = profile_name

    if helper_count is not None:
        profile.helper_count = helper_count

    if driver_first_trip_rate is not None:
        profile.driver_first_trip_rate = driver_first_trip_rate

    if driver_next_trip_rate is not None:
        profile.driver_next_trip_rate = driver_next_trip_rate

    if helper_first_trip_rate is not None:
        profile.helper_first_trip_rate = helper_first_trip_rate

    if helper_next_trip_rate is not None:
        profile.helper_next_trip_rate = helper_next_trip_rate

    if is_active is not None:
        profile.is_active = is_active

    profile.updated_by = current_user.id
    profile.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(profile)

    return api_response({"message": "Rate profile updated successfully"})


@router.delete("/rate-profiles/{profile_id}")
def delete_rate_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = db.query(TripRateProfile).filter(TripRateProfile.id == profile_id).first()

    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Profile not found",
        )

    profile.is_active = False
    profile.updated_by = current_user.id
    profile.updated_at = datetime.utcnow()

    db.commit()

    return api_response({"message": "Rate profile deactivated"})
