from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
)

from app.core.database import Base


class Holiday(Base):
    __tablename__ = "tpc_holidays"

    id = Column(Integer, primary_key=True, index=True)

    # Holiday Information
    holiday_name = Column(String(255), nullable=False)
    holiday_date = Column(Date, nullable=False, index=True)

    holiday_type = Column(String(50), nullable=False)

    scope = Column(String(50), nullable=False)

    province = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)

    # If true, this replaces the holiday coming from the API
    override_api = Column(Boolean, default=False)

    remarks = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )