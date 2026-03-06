# app/models/trips.py

import enum
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, ForeignKey, Enum, String, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class TripStatus(str, enum.Enum):
    ASSIGNED = "ASSIGNED"
    ACTIVE = "ACTIVE"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Trip(Base):
    __tablename__ = "tpc_trips"

    id = Column(Integer, primary_key=True, index=True)

    driver_id = Column(
        Integer, ForeignKey("tpc_users.id", ondelete="CASCADE"), nullable=False
    )
    ticket_no = Column(String(100), nullable=False, unique=True, index=True)
    origin_store_id = Column(Integer, ForeignKey("tpc_stores.id"), nullable=True)

    status = Column(
        Enum(TripStatus, name="trip_status_enum"),
        default=TripStatus.ACTIVE,
        nullable=False,
    )

    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    driver = relationship("User", back_populates="trips")

    stops = relationship(
        "TripStop", back_populates="trip", cascade="all, delete-orphan"
    )

    trip_helpers = relationship(
        "TripHelper", back_populates="trip", cascade="all, delete-orphan"
    )

    helpers = relationship(
        "Employee",
        secondary="tpc_trip_helpers",
        viewonly=True,
    )
    gps_logs = relationship(
        "GPSLog", back_populates="trip", cascade="all, delete-orphan"
    )

    origin_store = relationship("Store", foreign_keys=[origin_store_id])
