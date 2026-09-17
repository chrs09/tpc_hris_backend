from datetime import datetime
from sqlalchemy.orm import relationship

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
)

from app.core.database import Base


class TruckType(Base):
    """A vehicle classification (e.g. "6-Wheeler", "10-Wheeler Wingvan")
    with an associated size/capacity description -- assignable to
    VehicleUnit rows under Fleet Management. Managed by
    superadmin/admin under Fleet Management -> Truck Types."""

    __tablename__ = "tpc_truck_types"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False, unique=True)

    # Free text on purpose (e.g. "10 tons", "6-Wheeler Small", "40ft
    # Container") -- capacity/size conventions vary too much across
    # fleets to force into an enum.
    size = Column(String(100), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    vehicle_units = relationship("VehicleUnit", back_populates="truck_type")
