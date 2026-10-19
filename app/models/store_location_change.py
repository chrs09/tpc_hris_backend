from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class StoreLocationChange(Base):
    """Every change to a store's coordinates (Customers -> Location
    history): set from the drivers' unloading GPS (app/services/
    store_location.py), a suggestion accepted, or edited by hand."""

    __tablename__ = "tpc_store_location_changes"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("tpc_stores.id", ondelete="CASCADE"), nullable=False, index=True)
    old_latitude = Column(Float, nullable=True)
    old_longitude = Column(Float, nullable=True)
    new_latitude = Column(Float, nullable=False)
    new_longitude = Column(Float, nullable=False)
    # AUTO_FIRST / AUTO_CONSENSUS / SUGGESTION_ACCEPTED / MANUAL
    source = Column(String(30), nullable=False)
    sample_count = Column(Integer, nullable=True)
    driver_count = Column(Integer, nullable=True)
    note = Column(Text, nullable=True)
    changed_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    changed_by = relationship("User")
