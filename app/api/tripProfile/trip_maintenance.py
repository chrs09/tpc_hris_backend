from fastapi import APIRouter, Depends, HTTPException, Form
from datetime import datetime
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db

from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.vehicle_unit import VehicleUnit
from app.models.TripRate import TripRateProfile
from app.models.customer import Customer
from app.models.supplier import Supplier
from app.models.vehicle_maintenance import VehicleMaintenance
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


# =========================================================
# FLEET MANAGEMENT -- CUSTOMERS
#
# Simple contact-card CRUD for now (name/contact/phone/email/address),
# not yet linked to Trip/Store -- expected to grow once the actual
# usage of a "customer" in the trip flow is decided.
# =========================================================
@router.get("/customers")
def get_customers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customers = db.query(Customer).order_by(Customer.name.asc()).all()

    response = [
        {
            "id": customer.id,
            "name": customer.name,
            "contact_person": customer.contact_person,
            "phone": customer.phone,
            "email": customer.email,
            "address": customer.address,
            "is_active": customer.is_active,
        }
        for customer in customers
    ]

    return api_response(response)


@router.get("/customers/active")
def get_active_customers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customers = (
        db.query(Customer)
        .filter(Customer.is_active.is_(True))
        .order_by(Customer.name.asc())
        .all()
    )

    response = [
        {"id": customer.id, "name": customer.name} for customer in customers
    ]

    return api_response(response)


@router.post("/customers")
def create_customer(
    name: str = Form(...),
    contact_person: str = Form(None),
    phone: str = Form(None),
    email: str = Form(None),
    address: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = Customer(
        name=name,
        contact_person=contact_person,
        phone=phone,
        email=email,
        address=address,
        created_by=current_user.id,
    )

    db.add(customer)
    db.commit()
    db.refresh(customer)

    return api_response(
        {"message": "Customer created successfully", "id": customer.id}
    )


@router.patch("/customers/{customer_id}")
def update_customer(
    customer_id: int,
    name: str = Form(None),
    contact_person: str = Form(None),
    phone: str = Form(None),
    email: str = Form(None),
    address: str = Form(None),
    is_active: bool = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if name is not None:
        customer.name = name
    if contact_person is not None:
        customer.contact_person = contact_person
    if phone is not None:
        customer.phone = phone
    if email is not None:
        customer.email = email
    if address is not None:
        customer.address = address
    if is_active is not None:
        customer.is_active = is_active

    customer.updated_by = current_user.id
    customer.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(customer)

    return api_response({"message": "Customer updated successfully"})


@router.delete("/customers/{customer_id}")
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer.is_active = False
    customer.updated_by = current_user.id
    customer.updated_at = datetime.utcnow()

    db.commit()

    return api_response({"message": "Customer deactivated"})


# =========================================================
# FLEET MANAGEMENT -- SUPPLIERS
#
# Same simple contact-card CRUD shape as Customers above.
# =========================================================
@router.get("/suppliers")
def get_suppliers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    suppliers = db.query(Supplier).order_by(Supplier.name.asc()).all()

    response = [
        {
            "id": supplier.id,
            "name": supplier.name,
            "contact_person": supplier.contact_person,
            "phone": supplier.phone,
            "email": supplier.email,
            "address": supplier.address,
            "is_active": supplier.is_active,
        }
        for supplier in suppliers
    ]

    return api_response(response)


@router.get("/suppliers/active")
def get_active_suppliers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    suppliers = (
        db.query(Supplier)
        .filter(Supplier.is_active.is_(True))
        .order_by(Supplier.name.asc())
        .all()
    )

    response = [
        {"id": supplier.id, "name": supplier.name} for supplier in suppliers
    ]

    return api_response(response)


@router.post("/suppliers")
def create_supplier(
    name: str = Form(...),
    contact_person: str = Form(None),
    phone: str = Form(None),
    email: str = Form(None),
    address: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    supplier = Supplier(
        name=name,
        contact_person=contact_person,
        phone=phone,
        email=email,
        address=address,
        created_by=current_user.id,
    )

    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    return api_response(
        {"message": "Supplier created successfully", "id": supplier.id}
    )


@router.patch("/suppliers/{supplier_id}")
def update_supplier(
    supplier_id: int,
    name: str = Form(None),
    contact_person: str = Form(None),
    phone: str = Form(None),
    email: str = Form(None),
    address: str = Form(None),
    is_active: bool = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()

    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    if name is not None:
        supplier.name = name
    if contact_person is not None:
        supplier.contact_person = contact_person
    if phone is not None:
        supplier.phone = phone
    if email is not None:
        supplier.email = email
    if address is not None:
        supplier.address = address
    if is_active is not None:
        supplier.is_active = is_active

    supplier.updated_by = current_user.id
    supplier.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(supplier)

    return api_response({"message": "Supplier updated successfully"})


@router.delete("/suppliers/{supplier_id}")
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()

    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    supplier.is_active = False
    supplier.updated_by = current_user.id
    supplier.updated_at = datetime.utcnow()

    db.commit()

    return api_response({"message": "Supplier deactivated"})


# =========================================================
# FLEET MANAGEMENT -- VEHICLE MAINTENANCE
#
# One row per service/repair record for a VehicleUnit. Kept simple for
# now (free-text maintenance_type, no scheduling/reminders) -- expected
# to grow once actual usage is decided.
# =========================================================
def _serialize_maintenance(record: VehicleMaintenance) -> dict:
    return {
        "id": record.id,
        "vehicle_unit_id": record.vehicle_unit_id,
        "vehicle_unit": (
            {
                "id": record.vehicle_unit.id,
                "unit_code": record.vehicle_unit.unit_code,
                "plate_number": record.vehicle_unit.plate_number,
            }
            if record.vehicle_unit
            else None
        ),
        "maintenance_type": record.maintenance_type,
        "description": record.description,
        "service_date": record.service_date,
        "next_due_date": record.next_due_date,
        "odometer_reading": record.odometer_reading,
        "cost": record.cost,
    }


@router.get("/vehicle-maintenance")
def get_vehicle_maintenance_records(
    vehicle_unit_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(VehicleMaintenance).options(
        joinedload(VehicleMaintenance.vehicle_unit)
    )

    if vehicle_unit_id:
        query = query.filter(VehicleMaintenance.vehicle_unit_id == vehicle_unit_id)

    records = query.order_by(VehicleMaintenance.service_date.desc()).all()

    return api_response([_serialize_maintenance(record) for record in records])


@router.post("/vehicle-maintenance")
def create_vehicle_maintenance_record(
    vehicle_unit_id: int = Form(...),
    maintenance_type: str = Form(...),
    description: str = Form(None),
    service_date: datetime = Form(...),
    next_due_date: datetime = Form(None),
    odometer_reading: int = Form(None),
    cost: float = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    vehicle_unit = (
        db.query(VehicleUnit).filter(VehicleUnit.id == vehicle_unit_id).first()
    )

    if not vehicle_unit:
        raise HTTPException(status_code=404, detail="Vehicle unit not found")

    record = VehicleMaintenance(
        vehicle_unit_id=vehicle_unit_id,
        maintenance_type=maintenance_type,
        description=description,
        service_date=service_date,
        next_due_date=next_due_date,
        odometer_reading=odometer_reading,
        cost=cost,
        created_by=current_user.id,
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return api_response(
        {"message": "Maintenance record created successfully", "id": record.id}
    )


@router.patch("/vehicle-maintenance/{record_id}")
def update_vehicle_maintenance_record(
    record_id: int,
    maintenance_type: str = Form(None),
    description: str = Form(None),
    service_date: datetime = Form(None),
    next_due_date: datetime = Form(None),
    odometer_reading: int = Form(None),
    cost: float = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = (
        db.query(VehicleMaintenance)
        .filter(VehicleMaintenance.id == record_id)
        .first()
    )

    if not record:
        raise HTTPException(status_code=404, detail="Maintenance record not found")

    if maintenance_type is not None:
        record.maintenance_type = maintenance_type
    if description is not None:
        record.description = description
    if service_date is not None:
        record.service_date = service_date
    if next_due_date is not None:
        record.next_due_date = next_due_date
    if odometer_reading is not None:
        record.odometer_reading = odometer_reading
    if cost is not None:
        record.cost = cost

    record.updated_by = current_user.id
    record.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(record)

    return api_response({"message": "Maintenance record updated successfully"})


@router.delete("/vehicle-maintenance/{record_id}")
def delete_vehicle_maintenance_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = (
        db.query(VehicleMaintenance)
        .filter(VehicleMaintenance.id == record_id)
        .first()
    )

    if not record:
        raise HTTPException(status_code=404, detail="Maintenance record not found")

    db.delete(record)
    db.commit()

    return api_response({"message": "Maintenance record deleted"})
