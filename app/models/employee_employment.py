from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class EmployeeEmploymentHistory(Base):
    __tablename__ = "tpc_employee_employment_history"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=False)

    company_name = Column(String(150), nullable=True)
    position = Column(String(150), nullable=True)
    date_from = Column(Date, nullable=True)
    date_to = Column(Date, nullable=True)

    employee = relationship("Employee", back_populates="employment_history")