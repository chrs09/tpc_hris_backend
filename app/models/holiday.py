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
    UniqueConstraint,
)

from app.core.database import Base


class Holiday(Base):
    __tablename__ = "tpc_holidays"

    id = Column(Integer, primary_key=True, index=True)

    holiday_name = Column(String(255), nullable=False)
    holiday_date = Column(Date, nullable=False, index=True)
    holiday_type = Column(String(50), nullable=False)   # regular, special_non_working, special_working
    scope = Column(String(50), nullable=False)          # national, local

    province = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)

    source = Column(String(20), nullable=False, default="manual")  # "api" or "manual"
    override_api = Column(Boolean, default=False)  # manual holiday takes precedence over API on same date

    remarks = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("holiday_date", "source", "holiday_name", name="uq_holiday_date_source_name"),
    )