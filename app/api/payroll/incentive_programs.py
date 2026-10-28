# app/api/payroll/incentive_programs.py
#
# Incentive Policies: incentive programs per period (trip tiers, daily
# cash, long distance, complete attendance) and what each driver / helper
# earns under one. Amounts live on the program, so next month's memo is a
# copy with new numbers -- see app/services/incentives.py for the rules.

import json
from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.incentive_program import IncentiveProgram
from app.models.user import User
from app.services.incentives import (
    RULE_TYPES,
    IncentiveSettingsError,
    clean_settings,
    compute_program,
    load_settings,
    parse_applies_to,
)

router = APIRouter(prefix="/incentive-programs", tags=["Incentive Programs"])

# Coordinators read results too -- they hand out the daily cash.
_require_view = require_role_or_module(
    roles=["admin", "payroll_admin", "coordinator_admin"],
    module_key="payroll.incentive_policies",
)
_require_edit = require_role_or_module(
    roles=["admin", "payroll_admin"], module_key="payroll.incentive_policies"
)


class ProgramIn(BaseModel):
    name: str
    memo_no: str | None = None
    rule_type: str
    applies_to: list[str] | str = "drivers"
    period_start: date
    period_end: date
    release_date: date | None = None
    settings: dict = {}
    is_active: bool = True
    notes: str | None = None


class CopyIn(BaseModel):
    period_start: date
    period_end: date
    release_date: date | None = None
    memo_no: str | None = None


def _serialize(p: IncentiveProgram) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "memo_no": p.memo_no,
        "rule_type": p.rule_type,
        "rule_label": RULE_TYPES.get(p.rule_type, {}).get("label", p.rule_type),
        "applies_to": [g for g in (p.applies_to or "").split(",") if g],
        "period_start": p.period_start,
        "period_end": p.period_end,
        "release_date": p.release_date,
        "settings": load_settings(p),
        "is_active": p.is_active,
        "notes": p.notes,
        "updated_at": p.updated_at,
    }


def _get(db: Session, program_id: int) -> IncentiveProgram:
    p = db.query(IncentiveProgram).filter(IncentiveProgram.id == program_id).first()
    if p is None:
        raise HTTPException(status_code=404, detail="Incentive program not found.")
    return p


def _apply(p: IncentiveProgram, data: ProgramIn) -> None:
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    if data.period_end < data.period_start:
        raise HTTPException(status_code=400, detail="Period end can't be before its start.")
    if data.release_date and data.release_date < data.period_end:
        raise HTTPException(status_code=400, detail="Release date can't be before the period ends.")
    try:
        settings = clean_settings(data.rule_type, data.settings)
        groups = parse_applies_to(data.applies_to)
    except IncentiveSettingsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    p.name = name[:150]
    p.memo_no = (data.memo_no or "").strip()[:30] or None
    p.rule_type = data.rule_type
    p.applies_to = ",".join(groups)
    p.period_start = data.period_start
    p.period_end = data.period_end
    p.release_date = data.release_date
    p.settings = json.dumps(settings)
    p.is_active = data.is_active
    p.notes = (data.notes or "").strip() or None


@router.get("/rule-types")
def list_rule_types(current_user: User = Depends(_require_view)):
    """Each type's label and default settings, for the create form."""
    return [{"value": k, **v} for k, v in RULE_TYPES.items()]


@router.get("")
def list_programs(
    year: int | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
    rule_type: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    """Programs, latest period first; `year` (+ `month`) keeps the ones
    running in it."""
    q = db.query(IncentiveProgram)
    if year:
        start = date(year, month or 1, 1)
        end = date(year, month or 12, monthrange(year, month or 12)[1])
        q = q.filter(IncentiveProgram.period_start <= end, IncentiveProgram.period_end >= start)
    if rule_type:
        q = q.filter(IncentiveProgram.rule_type == rule_type)
    rows = q.order_by(IncentiveProgram.period_start.desc(), IncentiveProgram.id).all()
    return [_serialize(p) for p in rows]


@router.get("/{program_id}")
def get_program(
    program_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    return _serialize(_get(db, program_id))


@router.post("")
def create_program(
    data: ProgramIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_edit),
):
    p = IncentiveProgram(created_by_user_id=current_user.id, updated_by_user_id=current_user.id)
    _apply(p, data)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _serialize(p)


@router.put("/{program_id}")
def update_program(
    program_id: int,
    data: ProgramIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_edit),
):
    p = _get(db, program_id)
    _apply(p, data)
    p.updated_by_user_id = current_user.id
    db.commit()
    db.refresh(p)
    return _serialize(p)


@router.post("/{program_id}/copy")
def copy_program(
    program_id: int,
    data: CopyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_edit),
):
    """Next month's memo: same rule and amounts for a new period (edit the
    amounts after)."""
    src = _get(db, program_id)
    body = ProgramIn(
        name=src.name,
        memo_no=data.memo_no,
        rule_type=src.rule_type,
        applies_to=src.applies_to,
        period_start=data.period_start,
        period_end=data.period_end,
        release_date=data.release_date,
        settings=load_settings(src),
        is_active=True,
        notes=src.notes,
    )
    p = IncentiveProgram(created_by_user_id=current_user.id, updated_by_user_id=current_user.id)
    _apply(p, body)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _serialize(p)


@router.delete("/{program_id}")
def delete_program(
    program_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_edit),
):
    db.delete(_get(db, program_id))
    db.commit()
    return {"ok": True}


@router.get("/{program_id}/results")
def program_results(
    program_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    """What each driver / helper earns under the program -- so far while
    the period is still running (`is_final` false)."""
    return compute_program(db, _get(db, program_id))
