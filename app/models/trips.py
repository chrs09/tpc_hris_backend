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
    Text,
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

    # A comma-joined display string of every shipment number entered by
    # the coordinator at dispatch time (see shipment_numbers below for
    # the actual list) -- kept as its own column since most of the app
    # (payroll, office/finance review, trip tables, mobile) already reads
    # this single column to display "the shipment number(s)" for a trip.
    # Widened to fit up to 10 joined numbers (see MAX_SHIPMENT_NUMBERS in
    # app/api/driver/trips.py). Not by the driver at Checkout, which
    # dropped this field.
    ticket_no = Column(String(500), nullable=True, unique=True, index=True)

    # The full list of shipment numbers the coordinator entered at
    # dispatch (JSON-encoded list of strings, 1-10 entries -- a single
    # trip can cover multiple shipments, e.g. one truck carrying several
    # DRs/manifests). ticket_no above is always ", ".join(shipment_numbers).
    shipment_numbers = Column(Text, nullable=True)

    origin_store_id = Column(Integer, ForeignKey("tpc_stores.id"), nullable=True)

    # The trip's PRIMARY destination store -- always planned_store_ids[0],
    # kept as its own column (rather than only living inside the JSON list)
    # since most of the app (payroll, office/finance review, trip tables)
    # already reads this single column for display and for deriving
    # trip_rate_profile_id. Set at dispatch time now, not at Checkout.
    destination_store_id = Column(
        Integer, ForeignKey("tpc_stores.id"), nullable=True
    )

    # The full ordered list of destination stores the coordinator selected
    # at dispatch (JSON-encoded list of store ids, 1-20 entries -- see
    # MAX_PLANNED_STOPS in app/api/driver/trips.py). destination_store_id
    # above is always planned_store_ids[0]. The driver's "Arrived at
    # Store" step resolves each stop against whichever of these stores
    # haven't been delivered to yet (see check-in in
    # app/api/driver/trips.py), so this is the trip's actual multi-stop
    # route, not just a label.
    planned_store_ids = Column(Text, nullable=True)

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

    # Was `server_default=func.now()` -- that runs MySQL's own NOW(),
    # which reflects the DB server's local clock (PH time on this
    # deployment), not UTC. Every read of created_at then went through
    # utc_to_ph(), which treats naive datetimes as UTC and adds another
    # +8 on top -- double-offsetting every dispatch timestamp by 8
    # hours. Switched to the same Python-side datetime.utcnow() default
    # every other timestamp column on this model (and across the rest
    # of the app) already uses, so it's actually UTC going in.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # The coordinator/coordinator_admin who dispatched this trip --
    # nullable since trips created before this column existed have no
    # recorded dispatcher.
    dispatched_by_user_id = Column(
        Integer, ForeignKey("tpc_users.id"), nullable=True
    )

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

    driver = relationship("User", foreign_keys=[driver_id], back_populates="trips")

    dispatched_by = relationship("User", foreign_keys=[dispatched_by_user_id])

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
