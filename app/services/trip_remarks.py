from sqlalchemy.orm import Session, joinedload

from app.models.trip_bypass_log import TripBypassLog
from app.models.trip_remark import TripRemark
from app.models.user import User
from app.utils.timezone import utc_to_ph
from app.utils.user_display import display_name


def serialize_trip_remarks(db: Session, trip_id: int) -> list[dict]:
    """Remarks added to an approved trip (text and/or image), oldest
    first -- shared by the coordinator, Office and Finance review
    screens so every reviewer sees the same corrections."""
    rows = (
        db.query(TripRemark)
        .filter(TripRemark.trip_id == trip_id)
        .order_by(TripRemark.created_at.asc(), TripRemark.id.asc())
        .all()
    )
    user_ids = {r.created_by_user_id for r in rows}
    users = (
        {
            user.id: user
            for user in db.query(User)
            .options(joinedload(User.employee))
            .filter(User.id.in_(user_ids))
            .all()
        }
        if user_ids
        else {}
    )
    return [
        {
            "id": r.id,
            "text": r.text,
            "image_url": r.image_url,
            "created_by": (
                display_name(users[r.created_by_user_id])
                if r.created_by_user_id in users
                else None
            ),
            "created_at": (
                utc_to_ph(r.created_at).strftime("%b %d, %Y, %I:%M %p")
                if r.created_at
                else None
            ),
        }
        for r in rows
    ]


# Readable names for TripBypassLog.action values.
BYPASS_ACTION_LABELS = {
    "checkout": "Checkout",
    "check-in": "Arrived at Store",
    "start-unloading": "Start Unloading",
    "check-out": "Delivered",
    "checkin": "Checkin",
    "assign-store": "Linked stop to store",
    "edit": "Edited dispatch",
    "reorder": "Changed stop order",
    "cancel": "Cancelled trip",
    "manual-entry": "Manual trip entry",
    "manual-entry-approved": "Manual entry approved",
    "manual-entry-rejected": "Manual entry rejected",
}


def serialize_bypass_remarks(db: Session, trip_id: int) -> list[dict]:
    """Steps done on the driver's behalf (Trip Bypass, Trip Manual
    Entries, dispatch edits), each with who did it, when and the reason
    they gave -- oldest first. Shared by the coordinator and Office
    review screens."""
    logs = (
        db.query(TripBypassLog)
        .filter(TripBypassLog.trip_id == trip_id)
        .order_by(TripBypassLog.created_at.asc(), TripBypassLog.id.asc())
        .all()
    )
    user_ids = {log.performed_by_user_id for log in logs}
    users = (
        {
            user.id: user
            for user in db.query(User)
            .options(joinedload(User.employee))
            .filter(User.id.in_(user_ids))
            .all()
        }
        if user_ids
        else {}
    )
    return [
        {
            "id": log.id,
            "action": log.action,
            "action_label": BYPASS_ACTION_LABELS.get(log.action, log.action),
            "reason": log.reason,
            "performed_by": (
                display_name(users[log.performed_by_user_id])
                if log.performed_by_user_id in users
                else None
            ),
            "created_at": (
                utc_to_ph(log.created_at).strftime("%b %d, %Y, %I:%M %p")
                if log.created_at
                else None
            ),
        }
        for log in logs
    ]
