from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class EmployeeEducation(Base):
    __tablename__ = "tpc_employee_education"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=False)

    level = Column(String(50), nullable=True)
    institution = Column(String(150), nullable=True)
    degree = Column(String(150), nullable=True)
    year_from = Column(String(10), nullable=True)
    year_to = Column(String(10), nullable=True)
    skills = Column(String(255), nullable=True)

    employee = relationship("Employee", back_populates="education_records")
