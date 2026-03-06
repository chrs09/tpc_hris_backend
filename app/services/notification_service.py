from app.models.notification import Notification
from datetime import datetime


def create_notification(
    db, type_, driver_id=None, trip_id=None, trip_stop_id=None, message=None
):
    notification = Notification(
        type=type_,
        driver_id=driver_id,
        trip_id=trip_id,
        trip_stop_id=trip_stop_id,
        message=message,
        created_at=datetime.utcnow(),
        status="PENDING",
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification
