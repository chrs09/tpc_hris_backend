# app/api/banks.py
#
# Banks offered on the employee 201 form (Bank Type). Anyone logged in can
# read the list (the form needs it); adding / renaming / hiding is on
# Finance -> Bank Master (superadmin, or the finance.bank_master grant).
# There's no delete -- a bank that's no longer offered is hidden, so
# employees already on it keep it.

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role_or_module
from app.models.bank import Bank
from app.models.employee_bank import EmployeeBank
from app.models.user import User

router = APIRouter(prefix="/banks", tags=["Banks"])

_require_bank_master = require_role_or_module(
    roles=[], module_key="finance.bank_master"
)


class BankIn(BaseModel):
    name: str | None = None
    is_active: bool | None = None


def _clean(name: str | None) -> str:
    name = " ".join((name or "").split())
    if not name:
        raise HTTPException(status_code=400, detail="Enter the bank name.")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Bank name is too long.")
    return name


def _in_use(db: Session) -> dict:
    return dict(
        db.query(EmployeeBank.bank_type, func.count(EmployeeBank.id))
        .filter(EmployeeBank.bank_type.isnot(None))
        .group_by(EmployeeBank.bank_type)
        .all()
    )


def _serialize(bank: Bank, used: dict) -> dict:
    return {
        "id": bank.id,
        "name": bank.name,
        "is_active": bool(bank.is_active),
        "employee_count": used.get(bank.name, 0),
    }


def _get(db: Session, bank_id: int) -> Bank:
    bank = db.query(Bank).filter(Bank.id == bank_id).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found.")
    return bank


def _check_unique(db: Session, name: str, exclude_id: int | None = None):
    query = db.query(Bank.id).filter(func.lower(Bank.name) == name.lower())
    if exclude_id:
        query = query.filter(Bank.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=400, detail=f'"{name}" is already on the list.')


@router.get("")
def list_banks(
    include_hidden: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Active banks for the 201 form ("Other" last); Bank Master passes
    include_hidden=true to manage them all."""
    query = db.query(Bank)
    if not include_hidden:
        query = query.filter(Bank.is_active.is_(True))
    banks = sorted(query.all(), key=lambda b: (b.name.lower() == "other", b.name.lower()))
    used = _in_use(db)
    return [_serialize(b, used) for b in banks]


@router.post("")
def add_bank(
    payload: BankIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_bank_master),
):
    name = _clean(payload.name)
    _check_unique(db, name)
    bank = Bank(name=name, is_active=True)
    db.add(bank)
    db.commit()
    db.refresh(bank)
    return _serialize(bank, _in_use(db))


@router.patch("/{bank_id}")
def update_bank(
    bank_id: int,
    payload: BankIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_bank_master),
):
    """Rename (employees on the old name move to the new one) or
    hide / show it on the 201 form."""
    bank = _get(db, bank_id)
    if payload.name is not None:
        name = _clean(payload.name)
        if name != bank.name:
            _check_unique(db, name, exclude_id=bank.id)
            db.query(EmployeeBank).filter(EmployeeBank.bank_type == bank.name).update(
                {EmployeeBank.bank_type: name}, synchronize_session=False
            )
            bank.name = name
    if payload.is_active is not None:
        bank.is_active = payload.is_active
    db.commit()
    db.refresh(bank)
    return _serialize(bank, _in_use(db))

