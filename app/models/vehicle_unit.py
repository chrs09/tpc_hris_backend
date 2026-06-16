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

    trips = relationship(
        "Trip",
        back_populates="vehicle_unit",
    )
