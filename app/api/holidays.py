from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.holiday import Holiday
from app.schemas.holiday import HolidayCreate, HolidayResponse, HolidayUpdate
from app.services.holiday_service import (
    create_manual_holiday,
    delete_holiday,
    sync_holidays_from_api,
    update_holiday,
)

router = APIRouter(prefix="/holidays", tags=["holidays"])


@router.get("", response_model=list[HolidayResponse])
def list_holidays(
    year: int | None = Query(None),
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    query = select(Holiday)
    if year:
        query = query.where(extract("year", Holiday.holiday_date) == year)
    if active_only:
        query = query.where(Holiday.is_active.is_(True))
    return db.execute(query.order_by(Holiday.holiday_date)).scalars().all()


@router.get("/{holiday_id}", response_model=HolidayResponse)
def get_holiday(holiday_id: int, db: Session = Depends(get_db)):
    holiday = db.get(Holiday, holiday_id)
    if not holiday:
        raise HTTPException(404, "Holiday not found")
    return holiday


@router.post("", response_model=HolidayResponse, status_code=201)
def add_holiday(payload: HolidayCreate, db: Session = Depends(get_db)):
    return create_manual_holiday(db, payload)


@router.patch("/{holiday_id}", response_model=HolidayResponse)
def edit_holiday(holiday_id: int, payload: HolidayUpdate, db: Session = Depends(get_db)):
    holiday = update_holiday(db, holiday_id, payload)
    if not holiday:
        raise HTTPException(404, "Holiday not found")
    return holiday


@router.delete("/{holiday_id}", status_code=204)
def remove_holiday(holiday_id: int, db: Session = Depends(get_db)):
    if not delete_holiday(db, holiday_id):
        raise HTTPException(404, "Holiday not found")


@router.post("/sync/{year}")
async def sync_holidays(year: int, db: Session = Depends(get_db)):
    return await sync_holidays_from_api(db, year)