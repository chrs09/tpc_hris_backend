from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class EmployeeFamilyDetails(Base):
    __tablename__ = "tpc_employee_family_details"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), unique=True, nullable=False)

    spouse_name = Column(String(150), nullable=True)
    father_name = Column(String(150), nullable=True)
    mother_name = Column(String(150), nullable=True)

    employee = relationship("Employee", back_populates="family_details")