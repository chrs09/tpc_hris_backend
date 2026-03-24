from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.reminders import Reminder
from app.models.user import User
from app.schemas.reminder import ReminderCreate, ReminderResponse

router = APIRouter(prefix="/reminders", tags=["Reminders"])


@router.post("/", response_model=ReminderResponse)
def create_reminder(
    reminder_in: ReminderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Restrict to superadmin
    if current_user.role != "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Only superadmin can create reminders",
        )

    reminder = Reminder(
        message=reminder_in.message,
        created_by_user_id=current_user.id,
    )

    db.add(reminder)
    db.commit()
    db.refresh(reminder)

    return reminder


@router.get("/", response_model=List[ReminderResponse])
def get_reminders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "superadmin":
        return []

    reminders = (
        db.query(Reminder)
        .filter(Reminder.is_resolved.is_(False))
        .order_by(Reminder.created_at.desc())
        .all()
    )

    return [
        ReminderResponse(
            id=r.id,
            message=r.message,
            created_by_user_id=r.created_by_user_id,
            created_by_username=(
                r.created_by_user.username if r.created_by_user else None
            ),
            is_resolved=r.is_resolved,
            created_at=r.created_at,
        )
        for r in reminders
    ]


@router.patch("/{reminder_id}")
def resolve_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Not allowed")

    reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()

    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    reminder.is_resolved = True
    db.commit()

    return {"message": "Reminder resolved"}
