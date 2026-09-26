from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class FuelRequest(Base):
    """A driver's request for fuel (mobile Fuel tab).

    Flow (status):
      pending            driver sent odometer photo + plate number + city
      issued             coordinator admin gave a fuel code + liters
      receipt_submitted  driver uploaded the fuel receipt
      completed          coordinator admin confirmed the receipt
    Side exits: `declined` (coordinator admin turned the request down),
    `returned` (receipt sent back -- driver uploads again, same as issued),
    `cancelled` (driver withdrew it while still pending).
    """

    __tablename__ = "tpc_fuel_requests"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=True)

    # From the driver
    plate_number = Column(String(50), nullable=False)
    city = Column(String(120), nullable=False)
    odo_photo_url = Column(String(500), nullable=False)

    status = Column(String(30), nullable=False, default="pending", index=True)

    # From the coordinator admin
    fuel_code = Column(String(100), nullable=True)
    liters = Column(Numeric(10, 2), nullable=True)
    issued_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    issued_at = Column(DateTime, nullable=True)

    # After fueling
    receipt_photo_url = Column(String(500), nullable=True)
    receipt_submitted_at = Column(DateTime, nullable=True)

    completed_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Why it was declined, or why the receipt was sent back.
    note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    driver = relationship("User", foreign_keys=[user_id])
    employee = relationship("Employee", foreign_keys=[employee_id])
    issued_by = relationship("User", foreign_keys=[issued_by_user_id])
    completed_by = relationship("User", foreign_keys=[completed_by_user_id])
