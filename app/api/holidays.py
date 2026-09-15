from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role_or_module
from app.models.holiday import Holiday
from app.models.user import User
from app.schemas.holiday import HolidayCreate, HolidayResponse, HolidayUpdate
from app.services.holiday_service import (
    create_manual_holiday,
    delete_holiday,
    sync_holidays_from_api,
    update_holiday,
)

router = APIRouter(prefix="/holidays", tags=["holidays"])

# Reads are used by several other authenticated pages (Attendance, Payroll,
# AdminDashboard) for any logged-in user, not just Administrator grantees --
# these previously had NO auth check at all (not even a login requirement),
# a pre-existing gap found while wiring up Module Assignment for this group.
# Writes (create/edit/delete/sync) are the actual Holidays admin page, so
# those are gated to superadmin or an "administrator.holidays" grant.
_require_holidays_write_access = require_role_or_module(
    roles=[], module_key="administrator.holidays"
)


@router.get("", response_model=list[HolidayResponse])
def list_holidays(
    year: int | None = Query(None),
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Holiday)
    if year:
        query = query.where(extract("year", Holiday.holiday_date) == year)
    if active_only:
        query = query.where(Holiday.is_active.is_(True))
    return db.execute(query.order_by(Holiday.holiday_date)).scalars().all()


@router.get("/{holiday_id}", response_model=HolidayResponse)
def get_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    holiday = db.get(Holiday, holiday_id)
    if not holiday:
        raise HTTPException(404, "Holiday not found")
    return holiday


@router.post("", response_model=HolidayResponse, status_code=201)
def add_holiday(
    payload: HolidayCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_holidays_write_access),
):
    try:
        return create_manual_holiday(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/{holiday_id}", response_model=HolidayResponse)
def edit_holiday(
    holiday_id: int,
    payload: HolidayUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_holidays_write_access),
):
    try:
        holiday = update_holiday(db, holiday_id, payload)

        if not holiday:
            raise HTTPException(404, "Holiday not found")

        return holiday

    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/{holiday_id}", status_code=204)
def remove_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_holidays_write_access),
):
    if not delete_holiday(db, holiday_id):
        raise HTTPException(404, "Holiday not found")


@router.post("/sync/{year}")
async def sync_holidays(
    year: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_holidays_write_access),
):
    return await sync_holidays_from_api(db, year)