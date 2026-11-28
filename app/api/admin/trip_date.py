"""Change a trip's date / start time after the fact (superadmin only).
See app/services/trip_date_change.py for the rules."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_superadmin
from app.models.user import User
from app.services import trip_date_change as D

router = APIRouter(prefix="/admin/trip-date", tags=["Trip Date Change"])


class DateChange(BaseModel):
    date: date
    time: str | None = None  # "HH:MM" PH; blank keeps the trip's time
    reason: str


@router.get("/can-change")
def can_change(current_user: User = Depends(get_current_user)):
    role = getattr(current_user.role, "value", current_user.role)
    return {"can_change": str(role).lower() == "superadmin"}


@router.get("/trips/{trip_id}/check")
def check_date_change(
    trip_id: int,
    date: date,
    time: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Whether the trip can move to this date / time, and its place in
    the driver's day after the move."""
    return D.check(db, D.load_trip(db, trip_id), date, time)


@router.put("/trips/{trip_id}")
def change_trip_date(
    trip_id: int,
    payload: DateChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    if not (payload.reason or "").strip():
        raise HTTPException(status_code=400, detail="Give the reason for the change.")
    result = D.change(db, D.load_trip(db, trip_id), payload.date, payload.time, current_user, payload.reason)
    db.commit()
    return {**result, "message": f"Trip moved to {result['new']}."}
