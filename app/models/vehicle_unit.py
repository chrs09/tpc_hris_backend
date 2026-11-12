from datetime import datetime
from sqlalchemy.orm import relationship

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from app.core.database import Base


class VehicleUnit(Base):
    __tablename__ = "tpc_vehicle_units"

    id = Column(Integer, primary_key=True, index=True)

    unit_code = Column(
        String(50),
        nullable=True,
        unique=True,
    )

    plate_number = Column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )

    description = Column(
        String(255),
        nullable=True,
    )

    truck_type_id = Column(
        Integer,
        ForeignKey("tpc_truck_types.id"),
        nullable=True,
    )

    # CR (Certificate of Registration) and OR (Official Receipt) are two
    # separate physical documents, tracked separately here -- each has its
    # own live link to the actual scanned document (uploaded via
    # FileService.upload_vehicle_cr / upload_vehicle_or) and its own
    # renewal/expiration date, so the Vehicle List can flag either one
    # coming up for renewal independently.
    cr_number = Column(String(100), nullable=True)
    cr_document_url = Column(String(500), nullable=True)
    cr_expiration_date = Column(Date, nullable=True)

    or_number = Column(String(100), nullable=True)
    or_document_url = Column(String(500), nullable=True)
    or_expiration_date = Column(Date, nullable=True)

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    is_available = Column(
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

    # The driver this unit belongs to (one each way). Trip Assignment
    # picks it automatically; dispatching anyone else in it -- or this
    # driver in another unit -- needs a reason (app/services/vehicle_assignment.py).
    assigned_driver_id = Column(
        Integer, ForeignKey("tpc_users.id"), nullable=True, unique=True
    )
    assigned_driver = relationship("User", foreign_keys=[assigned_driver_id])

    # The company the unit belongs to (Administrator -> Companies). Set
    # and shown to the superadmin only; for future use.
    company_id = Column(Integer, ForeignKey("tpc_companies.id"), nullable=True, index=True)
    company = relationship("Company")

    # Fleet status set by Fleet Management (Vehicle List -> Set status):
    # available / breakdown / maintenance / hold / retired. "Assigned" and
    # "In transit" aren't stored -- they come from the unit's trips (see
    # app/services/fleet_status.py). Anything but available can't be
    # dispatched.
    fleet_status = Column(String(20), nullable=False, default="available", server_default="available")
    status_reason = Column(Text, nullable=True)
    status_since = Column(DateTime, nullable=True)
    # Expected back in service (breakdown / maintenance / hold), optional.
    status_until = Column(Date, nullable=True)
    status_updated_by = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    truck_type = relationship("TruckType", back_populates="vehicle_units")

    trips = relationship(
        "Trip",
        back_populates="vehicle_unit",
    )


class VehicleStatusLog(Base):
    """Each period a unit spent in a fleet status other than available
    (breakdown / maintenance / hold / retired) -- downtime for the Truck
    Utilization report. ended_at None = still in that status."""

    __tablename__ = "tpc_vehicle_status_logs"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_unit_id = Column(Integer, ForeignKey("tpc_vehicle_units.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False)
    reason = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
