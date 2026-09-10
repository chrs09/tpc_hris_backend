# app/models/trips.py

import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    ForeignKey,
    Enum,
    String,
    Boolean,
    func,
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class TripStatus(str, enum.Enum):
    ASSIGNED = "ASSIGNED"
    ACTIVE = "ACTIVE"

    # Driver completed trip.
    # Waiting for coordinator.
    PENDING_APPROVAL = "PENDING_APPROVAL"

    # Coordinator approved trip.
    # Waiting for office personnel.
    PENDING_OFFICE_REVIEW = "PENDING_OFFICE_REVIEW"

    # Office personnel reviewed trip.
    # Waiting for finance.
    PENDING_FINANCE_REVIEW = "PENDING_FINANCE_REVIEW"

    # Finance approved trip.
    COMPLETED = "COMPLETED"

    CANCELLED = "CANCELLED"


class Trip(Base):
    __tablename__ = "tpc_trips"

    id = Column(Integer, primary_key=True, index=True)

    driver_id = Column(
        Integer, ForeignKey("tpc_users.id", ondelete="CASCADE"), nullable=False
    )
    ticket_no = Column(String(100), nullable=False, unique=True, index=True)

    # Auto-generated, human-readable trip reference -- "YYYYMM-00001",
    # sequential per PH-local calendar month (resets to 00001 each new
    # month). Distinct from `id` (the DB primary key) and `ticket_no`
    # (freely typed by the driver/trip manager, e.g. a shipment number)
    # -- this one always exists and is assigned by the system, not
    # entered by anyone. See _generate_trip_code() in
    # app/api/driver/trips.py. Nullable only because trips created
    # before this column existed don't have one (backfilled by the
    # migration that added it, but kept nullable defensively).
    trip_code = Column(String(20), unique=True, nullable=True, index=True)

    origin_store_id = Column(Integer, ForeignKey("tpc_stores.id"), nullable=True)

    vehicle_unit_id = Column(
        Integer,
        ForeignKey("tpc_vehicle_units.id"),
        nullable=True,
    )

    trip_rate_profile_id = Column(
        Integer,
        ForeignKey("tpc_trip_rate_profiles.id"),
        nullable=True,
    )

    status = Column(
        Enum(TripStatus, name="trip_status_enum"),
        default=TripStatus.ACTIVE,
        nullable=False,
    )

    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # True when the driver was allowed to start this trip despite not
    # being within any hub's GPS radius (previously a hard block) -- lets
    # the trip proceed while flagging it for the trip manager to notice
    # on the Active Trips Monitoring page.
    started_outside_hub_range = Column(Boolean, default=False, nullable=False)

    # Soft delete for the Completed Trips list: archiving hides a trip
    # from that list (see get_completed_trips in app/api/admin/trips.py)
    # without deleting its row or any related stops/GPS logs/files, so
    # cleaning up a long completed-trips list never requires touching the
    # database directly.
    is_archived = Column(Boolean, default=False, nullable=False)
    archived_at = Column(DateTime, nullable=True)
    archived_by_user_id = Column(
        Integer, ForeignKey("tpc_users.id", ondelete="SET NULL"), nullable=True
    )

    # foreign_keys is required here now that Trip has a second FK to
    # tpc_users (archived_by_user_id) -- without it SQLAlchemy can't tell
    # which column this relationship should join on.
    driver = relationship(
        "User", back_populates="trips", foreign_keys=[driver_id]
    )

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

    vehicle_unit = relationship("VehicleUnit", foreign_keys=[vehicle_unit_id])

    trip_rate_profile = relationship(
        "TripRateProfile", foreign_keys=[trip_rate_profile_id]
    )

    # NEW — one finance review per trip, created when the coordinator approves
    finance_review = relationship(
        "TripFinanceReview",
        back_populates="trip",
        uselist=False,
        cascade="all, delete-orphan",
    )
