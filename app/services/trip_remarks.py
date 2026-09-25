from sqlalchemy.orm import Session, joinedload

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
