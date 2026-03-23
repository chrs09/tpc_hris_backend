from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class EmployeeGovernmentDetails(Base):
    __tablename__ = "tpc_employee_government_details"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), unique=True, nullable=False)

    sss_number = Column(String(50), nullable=True)
    philhealth_number = Column(String(50), nullable=True)
    pagibig_number = Column(String(50), nullable=True)
    tin_number = Column(String(50), nullable=True)

    employee = relationship("Employee", back_populates="government_details")