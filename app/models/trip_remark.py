from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from app.core.database import Base


class TripRemark(Base):
    """A note added to a trip after it was approved. Once a trip is
    approved its photos are locked (see replace_trip_file in
    app/api/admin/trips.py), so corrections or extra proof are recorded
    here instead: text, an image, or both."""

    __tablename__ = "tpc_trip_remarks"

    id = Column(Integer, primary_key=True, index=True)

    trip_id = Column(Integer, ForeignKey("tpc_trips.id"), nullable=False, index=True)

    text = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)

    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
