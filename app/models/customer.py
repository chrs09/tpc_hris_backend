from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
)

from app.core.database import Base


class Customer(Base):
    """Fleet Management > Customer List. Kept intentionally simple for
    now (contact-card style, no linkage to Trip/Store yet) -- expected to
    grow once the actual usage of a "customer" in the trip flow is
    decided."""

    __tablename__ = "tpc_customers"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(150), nullable=False, index=True)
    contact_person = Column(String(150), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(150), nullable=True)
    address = Column(String(255), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
