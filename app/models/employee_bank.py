from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from app.core.database import Base


class EmployeeBank(Base):
    __tablename__ = "tpc_employee_bank"

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(
        Integer, ForeignKey("tpc_employees.id"), nullable=False, unique=True
    )

    bank_type = Column(String(100), nullable=True)  # BDO, GoTyme, BPI, etc.
    account_name = Column(String(150), nullable=True)
    account_number = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    employee = relationship("Employee", back_populates="bank_details")
