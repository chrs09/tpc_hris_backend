from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.core.database import Base


class Bank(Base):
    """Banks offered on the employee 201 form (Bank Type), managed on
    Finance -> Bank Master instead of hard-coded. Hiding one
    (is_active False) drops it from the form but keeps it on employees
    who already use it."""

    __tablename__ = "tpc_banks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
