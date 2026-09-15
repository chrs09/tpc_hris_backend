from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from app.core.database import Base


class TripBypassLog(Base):
    """Audit trail for the Trip Bypass feature -- every action a
    superadmin or module-granted user performs on a driver's behalf
    (see app/api/admin/trip_bypass.py) is recorded here, since each one
    is overriding a safety check (geofence, ownership) that would
    otherwise block it."""

    __tablename__ = "tpc_trip_bypass_logs"

    id = Column(Integer, primary_key=True, index=True)

    trip_id = Column(Integer, ForeignKey("tpc_trips.id"), nullable=False)
    stop_id = Column(Integer, ForeignKey("tpc_trip_stops.id"), nullable=True)

    # The action performed, e.g. "checkout", "start", "check-in",
    # "start-unloading", "check-out", "back-to-source", "checkin".
    action = Column(String(50), nullable=False)

    performed_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)
    reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
