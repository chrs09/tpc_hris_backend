from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from app.core.database import Base


class Notification(Base):
    __tablename__ = "tpc_notifications"

    id = Column(Integer, primary_key=True, index=True)

    type = Column(String(100), nullable=False)

    driver_id = Column(Integer, ForeignKey("tpc_users.id"))
    trip_id = Column(Integer, ForeignKey("tpc_trips.id"))
    trip_stop_id = Column(Integer, ForeignKey("tpc_trip_stops.id"))

    message = Column(String(255))

    status = Column(String(50), default="PENDING")

    reviewed_by_admin_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    reviewed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
