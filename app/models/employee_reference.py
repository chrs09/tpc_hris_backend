from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class EmployeeReference(Base):
    __tablename__ = "tpc_employee_references"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=False)

    name = Column(String(150), nullable=True)
    position = Column(String(150), nullable=True)
    address = Column(String(255), nullable=True)
    contact = Column(String(50), nullable=True)

    employee = relationship("Employee", back_populates="references")
