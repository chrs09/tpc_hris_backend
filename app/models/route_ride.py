from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class RouteRide(Base):
    """A route ride: a driver riding along on another driver's trip.

    source "assigned": set in Trip Assignment (Is Route Ride) on a trip in
    progress -- the rider sees that trip in their app and can do its steps.
    source "manual": Route Ride Manual, for rides done before this existed
    (no trip): a date, how many, and the category (or an amount).

    Paid per ride: `amount` when typed, else the trip category's Route Ride
    rate on the ride date (app/services/trip_rates.py), x quantity.
    """

    __tablename__ = "tpc_route_rides"

    id = Column(Integer, primary_key=True, index=True)

    rider_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False, index=True)
    # The trip ridden on (assigned rides). NULL for manual ones.
    trip_id = Column(Integer, ForeignKey("tpc_trips.id"), nullable=True, index=True)

    source = Column(String(20), nullable=False, default="assigned")  # assigned / manual

    # Manual rides: the day, how many, and what they pay.
    ride_date = Column(Date, nullable=True, index=True)
    quantity = Column(Integer, nullable=False, default=1, server_default="1")
    trip_rate_profile_id = Column(
        Integer, ForeignKey("tpc_trip_rate_profiles.id"), nullable=True
    )
    # Typed amount per ride (overrides the category rate).
    amount = Column(Numeric(10, 2), nullable=True)

    notes = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    rider = relationship("User", foreign_keys=[rider_user_id])
    trip = relationship("Trip", foreign_keys=[trip_id])
    trip_rate_profile = relationship("TripRateProfile", foreign_keys=[trip_rate_profile_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
