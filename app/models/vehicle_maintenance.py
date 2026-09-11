from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class VehicleMaintenance(Base):
    """Fleet Management > Vehicle Maintenance. One row per service/repair
    record for a VehicleUnit -- kept simple for now (no maintenance-type
    enum, no scheduling/reminders) since this is a first pass, expected
    to grow once actual usage is decided."""

    __tablename__ = "tpc_vehicle_maintenance"

    id = Column(Integer, primary_key=True, index=True)

    vehicle_unit_id = Column(
        Integer, ForeignKey("tpc_vehicle_units.id"), nullable=False, index=True
    )

    maintenance_type = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    service_date = Column(DateTime, nullable=False)
    next_due_date = Column(DateTime, nullable=True)
    odometer_reading = Column(Integer, nullable=True)
    cost = Column(Float, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)

    vehicle_unit = relationship("VehicleUnit")
