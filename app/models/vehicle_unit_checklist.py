from datetime import datetime
from sqlalchemy.orm import relationship

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
)

from app.core.database import Base


class VehicleUnitChecklist(Base):
    """One compliance/documentation checklist per VehicleUnit -- the
    acquisition/renewal paperwork checklist (Documentation, Provisional
    Authority, Certificate of Public Convenience, Renewal, Grab),
    vehicle master details (owner, VIN, engine #, etc.), and loan
    agency/LTMS account details. The section/item structure is defined
    on the frontend (CHECKLIST_SCHEMA in TripMaintenance.jsx) -- this
    table just stores whatever's been filled in as one JSON blob per
    vehicle unit, keyed by section:
    {
      "documentation": {"checked": true, "items": {"deed_of_sale": true, ...}},
      "vehicle_details": {"checked": true, "items": {"owner_first_name": "Juan", ...}},
      ...
    }
    Keeping this schema-flexible (JSON) instead of ~50 individual
    columns avoids a migration every time a checklist item is
    added/renamed/reworded."""

    __tablename__ = "tpc_vehicle_unit_checklists"

    id = Column(Integer, primary_key=True, index=True)

    vehicle_unit_id = Column(
        Integer,
        ForeignKey("tpc_vehicle_units.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    data = Column(Text, nullable=True)

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    updated_by = Column(Integer, nullable=True)

    vehicle_unit = relationship("VehicleUnit")
