from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class TripCorrection(Base):
    """A requested change to a finished trip (Trip Management -> Correction
    Requests). Coordinators / operations request it with a reason; Finance
    approves or rejects. Only on approval is the trip changed, and the
    values it had before are kept here (`original`) -- the original data is
    never lost. Allowed until the trip is Cleared by Finance and while its
    payroll isn't locked (app/services/trip_corrections.py)."""

    __tablename__ = "tpc_trip_corrections"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("tpc_trips.id"), nullable=False, index=True)
    # pending / approved / rejected / cancelled
    status = Column(String(20), nullable=False, default="pending", index=True)

    reason = Column(Text, nullable=False)
    # JSON {field: new value} -- what the requester wants.
    requested = Column(Text, nullable=False)
    # JSON {field: value} -- the trip's values when requested (shown as
    # "from"), then again exactly as replaced when approved.
    original = Column(Text, nullable=False)

    requested_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    decided_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decision_note = Column(Text, nullable=True)

    trip = relationship("Trip")
    requested_by = relationship("User", foreign_keys=[requested_by_user_id])
    decided_by = relationship("User", foreign_keys=[decided_by_user_id])
