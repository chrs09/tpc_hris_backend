# app/models/trip_helpers.py

from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class TripHelper(Base):
    __tablename__ = "tpc_trip_helpers"

    id = Column(Integer, primary_key=True)

    trip_id = Column(
        Integer, ForeignKey("tpc_trips.id", ondelete="CASCADE"), nullable=False
    )

    helper_id = Column(
        Integer, ForeignKey("tpc_employees.id", ondelete="CASCADE"), nullable=False
    )

    # Relationships
    trip = relationship("Trip", back_populates="trip_helpers")
    helper = relationship("Employee", back_populates="trip_assignments")
