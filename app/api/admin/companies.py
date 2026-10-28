# app/api/admin/companies.py
#
# Administrator -> Companies: the companies in the group. For now a
# vehicle unit can be tagged with the company it belongs to (Fleet
# Management); kept for future use elsewhere. Superadmin only -- reading
# and changing.

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_superadmin
from app.models.company import Company
from app.models.user import User
from app.models.vehicle_unit import VehicleUnit

router = APIRouter(prefix="/companies", tags=["Companies"])


class CompanyIn(BaseModel):
    name: str
    code: str | None = None
    tin: str | None = None
    address: str | None = None
    contact_person: str | None = None
    contact_number: str | None = None
    notes: str | None = None
    is_active: bool = True


def _clean(value, length):
    value = (value or "").strip()
    return value[:length] or None


def _serialize(company: Company, vehicle_count: int = 0) -> dict:
    return {
        "id": company.id,
        "name": company.name,
        "code": company.code,
        "tin": company.tin,
        "address": company.address,
        "contact_person": company.contact_person,
        "contact_number": company.contact_number,
        "notes": company.notes,
        "is_active": company.is_active,
        "vehicle_count": vehicle_count,
        "updated_at": company.updated_at,
    }


def _vehicle_counts(db: Session) -> dict:
    return dict(
        db.query(VehicleUnit.company_id, func.count(VehicleUnit.id))
        .filter(VehicleUnit.company_id.isnot(None))
        .group_by(VehicleUnit.company_id)
        .all()
    )


def _apply(db: Session, company: Company, data: CompanyIn) -> None:
    name = _clean(data.name, 150)
    if not name:
        raise HTTPException(status_code=400, detail="Company name is required.")
    clash = (
        db.query(Company.id)
        .filter(func.lower(Company.name) == name.lower(), Company.id != (company.id or 0))
        .first()
    )
    if clash:
        raise HTTPException(status_code=400, detail="A company with that name already exists.")
    company.name = name
    company.code = _clean(data.code, 30)
    company.tin = _clean(data.tin, 30)
    company.address = _clean(data.address, 255)
    company.contact_person = _clean(data.contact_person, 150)
    company.contact_number = _clean(data.contact_number, 50)
    company.notes = (data.notes or "").strip() or None
    company.is_active = data.is_active


@router.get("")
def list_companies(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    counts = _vehicle_counts(db)
    rows = db.query(Company).order_by(Company.is_active.desc(), Company.name).all()
    return [_serialize(c, counts.get(c.id, 0)) for c in rows]


@router.post("")
def create_company(
    data: CompanyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    company = Company(created_by_user_id=current_user.id)
    _apply(db, company, data)
    db.add(company)
    db.commit()
    db.refresh(company)
    return _serialize(company)


@router.put("/{company_id}")
def update_company(
    company_id: int,
    data: CompanyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    _apply(db, company, data)
    db.commit()
    db.refresh(company)
    return _serialize(company, _vehicle_counts(db).get(company.id, 0))


@router.delete("/{company_id}")
def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Deletes an unused company; one with vehicles must be deactivated
    instead."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    in_use = _vehicle_counts(db).get(company.id, 0)
    if in_use:
        raise HTTPException(
            status_code=400,
            detail=f"{in_use} vehicle unit(s) belong to this company -- deactivate it instead.",
        )
    db.delete(company)
    db.commit()
    return {"ok": True}
