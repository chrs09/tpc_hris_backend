from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class EmployeeEmergencyContact(Base):
    __tablename__ = "tpc_employee_emergency_contacts"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=False)

    contact_name = Column(String(150), nullable=True)
    relationship_type = Column(String(100), nullable=True)
    contact_number = Column(String(50), nullable=True)

    employee = relationship("Employee", back_populates="emergency_contacts")
