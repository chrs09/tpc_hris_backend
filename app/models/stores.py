# ==========================================
# IMPORTS
# ==========================================

from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import relationship
from app.core.database import Base

# ==========================================
# STORE MODEL
# ==========================================


class Store(Base):
    __tablename__ = "tpc_stores"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(150), nullable=False)

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    allowed_radius_meters = Column(Integer, default=100, nullable=False)

    # Relationships
    trip_stops = relationship("TripStop", back_populates="store", cascade="all, delete")
