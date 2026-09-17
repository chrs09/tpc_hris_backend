from datetime import datetime
from sqlalchemy.orm import relationship

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
)

from app.core.database import Base


class VehicleUnitORHistory(Base):
    """A snapshot of a VehicleUnit's OR (Official Receipt) fields taken
    right before they're overwritten by a renewal -- lets the Vehicle
    List show "previous OR number(s)" after each renewal instead of
    silently losing the old number. CR has no equivalent history since
    the CR (Certificate of Registration) never expires/renews in PH LTO
    rules -- only the OR does."""

    __tablename__ = "tpc_vehicle_unit_or_history"

    id = Column(Integer, primary_key=True, index=True)

    vehicle_unit_id = Column(
        Integer,
        ForeignKey("tpc_vehicle_units.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    or_number = Column(String(100), nullable=True)
    or_document_url = Column(String(500), nullable=True)
    or_expiration_date = Column(Date, nullable=True)

    # When this OR was superseded by a renewal (i.e. when the history
    # row was written), not when the OR itself was originally issued.
    replaced_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    replaced_by = Column(Integer, nullable=True)

    vehicle_unit = relationship("VehicleUnit")
