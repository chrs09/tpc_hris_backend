from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class TicketCategory(Base):
    """What a ticket is about (Trip / Delivery, Technical / System, ...)
    and which Org Chart unit handles it -- a new ticket in this category
    goes to that unit's least-busy person. `is_public` categories can be
    picked on the public support form (customers, stores)."""

    __tablename__ = "tpc_ticket_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=True)
    org_unit_id = Column(Integer, ForeignKey("tpc_org_units.id"), nullable=True)
    is_public = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    org_unit = relationship("OrgUnit")
