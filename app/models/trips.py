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

    # Nullable now -- a dispatched trip has no shipment number until the
    # driver completes the Checkout step and it's filled in (OCR-assisted
    # or manually). MySQL unique indexes allow multiple NULLs, so this is
    # safe pre-Checkout.
    ticket_no = Column(String(100), nullable=True, unique=True, index=True)
    origin_store_id = Column(Integer, ForeignKey("tpc_stores.id"), nullable=True)

    # Destination store for this trip, confirmed at Checkout (auto-matched
    # from the uploaded Invoice/LM via OCR, editable by the driver).
    destination_store_id = Column(
        Integer, ForeignKey("tpc_stores.id"), nullable=True
    )

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

    # Fine-grained progress through the 7-step driver flow (ASSIGNED,
    # CHECKOUT, IN_TRANSIT, ARRIVED, UNLOADING, DELIVERED, RETURNING,
    # CHECKIN). Kept deliberately separate from `status` above -- `status`
    # stays coarse for office/finance reporting (existing screens key off
    # it), while `current_step` is only for driving the mobile app's next
    # action button. Free text, not a DB enum, since these values are an
    # internal UI concern rather than a reporting dimension.
    current_step = Column(String(20), nullable=False, default="ASSIGNED")

    # Odometer reading the driver enters at Checkout, before Start Trip.
    odometer_reading = Column(Integer, nullable=True)

    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # True when the driver was allowed to start this trip despite not
    # being within any hub's GPS radius (previously a hard block) -- lets
    # the trip proceed while flagging it for the trip manager to notice
    # on the Active Trips Monitoring page.
    started_outside_hub_range = Column(Boolean, default=False, nullable=False)

    # These columns already existed on the live DB (added outside of a
    # tracked migration at some point) but were never mapped on this
    # model, so the ORM never set is_archived on insert -- since it's
    # NOT NULL with no DB default, every trip creation failed. Mapping
    # them here (with is_archived defaulting to False) fixes that.
    is_archived = Column(Boolean, default=False, nullable=False)
    archived_at = Column(DateTime, nullable=True)
    archived_by_user_id = Column(Integer, nullable=True)
    trip_code = Column(String(20), nullable=True)
    trip_category = Column(String(50), nullable=True)

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

    destination_store = relationship("Store", foreign_keys=[destination_store_id])

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
