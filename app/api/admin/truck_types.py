# app/api/admin/truck_types.py
#
# Vehicle classifications (e.g. "6-Wheeler", "10-Wheeler Wingvan") with
# a size/capacity description -- assignable to Vehicle Units under
# Fleet Management. Superadmin/admin can add, edit, and delete these
# (delete is blocked if any vehicle unit is still using it, to avoid
# orphaning that assignment).
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.truck_type import TruckType
from app.models.vehicle_unit import VehicleUnit

router = APIRouter(prefix="/admin/truck-types", tags=["Admin Truck Types"])


class TruckTypeCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    size: Optional[str] = None


class TruckTypeUpdateRequest(BaseModel):
    name: Optional[str] = None
    size: Optional[str] = None


def _build_response(truck_type: TruckType) -> dict:
    return {
        "id": truck_type.id,
        "name": truck_type.name,
        "size": truck_type.size,
        "is_active": truck_type.is_active,
    }


@router.get("/")
def get_truck_types(
    db: Session = Depends(get_db),
    current_admin=Depends(
        require_role_or_module(
            roles=["admin", "superadmin", "coordinator_admin"],
            module_key="fleet_management.truck_types",
        )
    ),
):
    truck_types = (
        db.query(TruckType)
        .filter(TruckType.is_active.is_(True))
        .order_by(TruckType.name.asc())
        .all()
    )
    return [_build_response(t) for t in truck_types]


@router.post("/")
def create_truck_type(
    payload: TruckTypeCreateRequest,
    db: Session = Depends(get_db),
    current_admin=Depends(
        require_role_or_module(
            roles=["admin", "superadmin", "coordinator_admin"],
            module_key="fleet_management.truck_types",
        )
    ),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Truck type name is required.")

    existing = db.query(TruckType).filter(TruckType.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="This truck type already exists.")

    truck_type = TruckType(
        name=name,
        size=(payload.size or "").strip() or None,
    )
    db.add(truck_type)
    db.commit()
    db.refresh(truck_type)

    return _build_response(truck_type)


@router.patch("/{truck_type_id}")
def update_truck_type(
    truck_type_id: int,
    payload: TruckTypeUpdateRequest,
    db: Session = Depends(get_db),
    current_admin=Depends(
        require_role_or_module(
            roles=["admin", "superadmin", "coordinator_admin"],
            module_key="fleet_management.truck_types",
        )
    ),
):
    truck_type = db.query(TruckType).filter(TruckType.id == truck_type_id).first()
    if not truck_type:
        raise HTTPException(status_code=404, detail="Truck type not found.")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Truck type name is required.")
        existing = (
            db.query(TruckType)
            .filter(TruckType.name == name, TruckType.id != truck_type_id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400, detail="This truck type already exists."
            )
        truck_type.name = name

    if payload.size is not None:
        truck_type.size = payload.size.strip() or None

    db.commit()
    db.refresh(truck_type)

    return _build_response(truck_type)


@router.delete("/{truck_type_id}")
def delete_truck_type(
    truck_type_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(
        require_role_or_module(
            roles=["admin", "superadmin", "coordinator_admin"],
            module_key="fleet_management.truck_types",
        )
    ),
):
    truck_type = db.query(TruckType).filter(TruckType.id == truck_type_id).first()
    if not truck_type:
        raise HTTPException(status_code=404, detail="Truck type not found.")

    in_use = (
        db.query(VehicleUnit)
        .filter(VehicleUnit.truck_type_id == truck_type_id)
        .count()
    )
    if in_use:
        raise HTTPException(
            status_code=400,
            detail=f"Can't delete -- {in_use} vehicle unit(s) are still using this truck type.",
        )

    db.delete(truck_type)
    db.commit()

    return {"message": "Truck type deleted."}
