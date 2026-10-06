from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class TripRateRule(Base):
    """A driver/helper trip rate that applies when a trip matches it.

    Every match field is optional -- blank means "any":
      - trip_rate_profile_id: the trip category (e.g. Core no helpers)
      - truck_type_id: the truck used on the trip (e.g. Wingvan)
      - origin_store_id + destination_area: the lane (e.g. Cebu hub ->
        Bohol), for source/destination rates like dump trucks

    Every rate is optional too -- blank means "keep the rate from a less
    specific rule, or the category". The rule in effect on the trip date
    (latest effective_from on or before it) wins; see
    app/services/trip_rates.py."""

    __tablename__ = "tpc_trip_rate_rules"

    id = Column(Integer, primary_key=True, index=True)

    trip_rate_profile_id = Column(
        Integer, ForeignKey("tpc_trip_rate_profiles.id"), nullable=True, index=True
    )
    truck_type_id = Column(
        Integer, ForeignKey("tpc_truck_types.id"), nullable=True, index=True
    )
    origin_store_id = Column(
        Integer, ForeignKey("tpc_stores.id"), nullable=True, index=True
    )
    destination_area = Column(String(100), nullable=True, index=True)
    # One exact outlet (beats an area).
    destination_store_id = Column(
        Integer, ForeignKey("tpc_stores.id"), nullable=True, index=True
    )

    driver_first_trip_rate = Column(Numeric(10, 2), nullable=True)
    driver_next_trip_rate = Column(Numeric(10, 2), nullable=True)
    helper_first_trip_rate = Column(Numeric(10, 2), nullable=True)
    helper_next_trip_rate = Column(Numeric(10, 2), nullable=True)

    effective_from = Column(Date, nullable=False, index=True)
    notes = Column(String(255), nullable=True)

    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    trip_rate_profile = relationship("TripRateProfile")
    truck_type = relationship("TruckType")
    origin_store = relationship("Store", foreign_keys=[origin_store_id])
    destination_store = relationship("Store", foreign_keys=[destination_store_id])
