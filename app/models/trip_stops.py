# app/models/trip_stops.py

import enum
from datetime import datetime
from sqlalchemy import Column, Integer, Float, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.core.database import Base


class StopStatus(str, enum.Enum):
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"


class TripStop(Base):
    __tablename__ = "tpc_trip_stops"

    id = Column(Integer, primary_key=True, index=True)

    trip_id = Column(
        Integer, ForeignKey("tpc_trips.id", ondelete="CASCADE"), nullable=False
    )

    store_id = Column(Integer, ForeignKey("tpc_stores.id"), nullable=True)

    status = Column(Enum(StopStatus, name="stop_status_enum"), nullable=False)

    check_in_time = Column(DateTime, nullable=True)
    lat_in = Column(Float, nullable=True)
    long_in = Column(Float, nullable=True)

    check_out_time = Column(DateTime, nullable=True)
    lat_out = Column(Float, nullable=True)
    long_out = Column(Float, nullable=True)

    requires_review = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    trip = relationship("Trip", back_populates="stops")
    store = relationship("Store")

    gps_logs = relationship(
        "GPSLog", back_populates="trip_stop", cascade="all, delete-orphan"
    )
