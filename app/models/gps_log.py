# ==========================================
# IMPORTS
# ==========================================

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Enum,
    Index,
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.trip_models import GPSActionType

# ==========================================
# ENUM
# ==========================================


# class GPSActionType(str, enum.Enum):
#     TRACK       = "TRACK"
#     CHECK_IN    = "CHECK_IN"
#     CHECK_OUT   = "CHECK_OUT"
# ==========================================
# GPS LOG MODEL
# ==========================================
class GPSLog(Base):
    __tablename__ = "tpc_gps_logs"
    # Composite index for fast trip route queries
    __table_args__ = (Index("ix_gps_trip_created", "trip_id", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)

    # Reference to trip
    trip_id = Column(
        Integer,
        ForeignKey("tpc_trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional reference to stop
    trip_stop_id = Column(
        Integer, ForeignKey("tpc_trip_stops.id", ondelete="CASCADE"), nullable=True
    )

    # Action type
    action_type = Column(
        Enum(GPSActionType, name="gps_action_enum"), nullable=False, index=True
    )

    # Actual GPS location of driver
    actual_lat = Column(Float, nullable=False)
    actual_long = Column(Float, nullable=False)

    # Store location (only used for check-in validation)
    store_lat = Column(Float, nullable=True)
    store_long = Column(Float, nullable=True)

    # Distance from store (meters)
    calculated_distance = Column(Float, nullable=True)

    # If location validation passed
    is_valid = Column(Boolean, nullable=True)

    # Optional GPS metrics
    accuracy = Column(Float, nullable=True)
    speed = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    trip = relationship("Trip", back_populates="gps_logs")

    trip_stop = relationship("TripStop", back_populates="gps_logs")
