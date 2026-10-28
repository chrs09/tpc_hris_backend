from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class Company(Base):
    """A company in the group (the company a vehicle unit belongs to, for
    now). Kept on Administrator -> Companies; superadmin only. A company
    in use is deactivated rather than deleted."""

    __tablename__ = "tpc_companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, unique=True)
    code = Column(String(30), nullable=True)
    tin = Column(String(30), nullable=True)
    address = Column(String(255), nullable=True)
    contact_person = Column(String(150), nullable=True)
    contact_number = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
