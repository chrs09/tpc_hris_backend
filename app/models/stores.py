# ==========================================
# IMPORTS
# ==========================================

import enum
from sqlalchemy import Boolean, Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class StoreProfile(str, enum.Enum):
    DP = "DP"  # Core A - No Helper
    KD = "KD"  # Core B - No Helper
    KA = "KA"  # Key Accounts
    PUP = "PUP"  # Core C - No Helper
    WS = "WS"  # Wholesaler


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
    required_helper = Column(Integer, default=0, nullable=False)

    # Marks a row as a company hub/origin point (yard, plant, satellite
    # office) rather than a delivery destination. Required by:
    #   - app/api/driver/trips.py:get_available_stores() -- hubs are
    #     excluded from the "select store" dropdown when starting a trip,
    #     since a driver delivers TO a store, not to a hub.
    #   - app/api/driver/trips.py:complete_trip() -- a trip can only be
    #     completed once the driver's GPS is back within range of a hub.
    # Previously both of those matched on a hardcoded set of store names
    # (e.g. {"Yard", "Plant", "Consolacion"}); this column replaces that
    # name-matching with a real, admin-editable flag on the store record.
    is_hub = Column(Boolean, default=False, nullable=False)

    # LEGACY: kept temporarily for safe rollout. Do not write new code
    # that depends on this column -- use trip_rate_profile_id instead.
    # Remove this column + the StoreProfile enum once trip_rate_profile_id
    # is confirmed populated for all stores in production.
    profile = Column(String(50), nullable=True, default="DP")

    # NEW: single source of truth for a store's trip category / rate profile.
    trip_rate_profile_id = Column(
        Integer,
        ForeignKey("tpc_trip_rate_profiles.id"),
        nullable=True,  # nullable during rollout; tighten to False after backfill
        index=True,
    )

    # Relationships
    trip_stops = relationship("TripStop", back_populates="store", cascade="all, delete")
    trip_rate_profile = relationship("TripRateProfile", back_populates="stores")