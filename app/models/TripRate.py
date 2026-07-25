# app/models/trip_rate_profile.py

from datetime import datetime
from sqlalchemy.orm import relationship

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
)

from app.core.database import Base


class TripRateProfile(Base):
    __tablename__ = "tpc_trip_rate_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # NEW: short, stable code used to link Store -> TripRateProfile
    # (e.g. "DP", "KA", "WS"). This is now the single source of truth
    # for trip category codes -- Store no longer defines its own enum.
    code = Column(
        String(20),
        nullable=True,  # nullable for now during rollout; backfill then tighten
        unique=True,
        index=True,
    )

    profile_name = Column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    helper_count = Column(
        Integer,
        nullable=False,
        default=0,
    )

    driver_first_trip_rate = Column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    driver_next_trip_rate = Column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    helper_first_trip_rate = Column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    helper_next_trip_rate = Column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    created_by = Column(
        Integer,
        nullable=True,
    )

    updated_by = Column(
        Integer,
        nullable=True,
    )

    trips = relationship(
        "Trip",
        back_populates="trip_rate_profile",
    )

    stores = relationship(
        "Store",
        back_populates="trip_rate_profile",
    )