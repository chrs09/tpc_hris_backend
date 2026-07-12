# app/models/dispatch_item.py

from datetime import datetime
import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Enum,
)

from sqlalchemy.orm import relationship

from app.core.database import Base


class DispatchItemStatus(str, enum.Enum):
    ASSIGNED = "ASSIGNED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class DispatchItem(Base):
    __tablename__ = "tpc_dispatch_items"

    id = Column(Integer, primary_key=True, index=True)

    dispatch_id = Column(
        Integer,
        ForeignKey(
            "tpc_dispatches.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    shipment_no = Column(
        String(100),
        nullable=False,
        index=True,
    )

    dealer_name = Column(
        String(255),
        nullable=False,
    )

    hauler_name = Column(
        String(255),
        nullable=True,
    )

    pallets = Column(
        Integer,
        nullable=False,
        default=0,
    )

    cases = Column(
        Integer,
        nullable=False,
        default=0,
    )

    driver_id = Column(
        Integer,
        ForeignKey("tpc_users.id"),
        nullable=False,
    )

    vehicle_unit_id = Column(
        Integer,
        ForeignKey("tpc_vehicle_units.id"),
        nullable=False,
    )

    trip_rate_profile_id = Column(
        Integer,
        ForeignKey("tpc_trip_rate_profiles.id"),
        nullable=False,
    )

    status = Column(
        Enum(
            DispatchItemStatus,
            name="dispatch_item_status_enum",
        ),
        nullable=False,
        default=DispatchItemStatus.ASSIGNED,
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

    dispatch = relationship(
        "Dispatch",
        back_populates="items",
    )

    driver = relationship(
        "User",
        foreign_keys=[driver_id],
    )

    vehicle = relationship(
        "VehicleUnit",
        foreign_keys=[vehicle_unit_id],
    )

    trip_rate_profile = relationship(
        "TripRateProfile",
        foreign_keys=[trip_rate_profile_id],
    )

    helpers = relationship(
        "DispatchHelper",
        back_populates="dispatch_item",
        cascade="all, delete-orphan",
    )