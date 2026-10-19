from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from app.core.database import Base


class PhotoSeal(Base):
    """One row per photo stamped by the system (app/services/watermark.py):
    its reference code (printed on the photo), the SHA-256 of the exact
    file stored, and when / where it was taken. Administrator -> Verify
    Photo checks a photo against this -- a cropped, edited or re-pasted
    image no longer matches."""

    __tablename__ = "tpc_photo_seals"

    id = Column(Integer, primary_key=True, index=True)
    ref = Column(String(20), nullable=False, unique=True, index=True)
    sha256 = Column(String(64), nullable=False, index=True)
    file_url = Column(String(500), nullable=True)
    captured_at = Column(DateTime, nullable=False)  # UTC
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    label = Column(Text, nullable=True)  # location line, e.g. "TPC Yard (42m)"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
