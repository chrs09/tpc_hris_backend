from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class EmployeePersonalDetails(Base):
    __tablename__ = "tpc_employee_personal_details"

    id = Column(Integer, primary_key=True)
    employee_id = Column(
        Integer, ForeignKey("tpc_employees.id"), unique=True, nullable=False
    )

    birthday = Column(Date, nullable=True)
    birthplace = Column(String(150), nullable=True)
    gender = Column(String(50), nullable=True)
    civil_status = Column(String(50), nullable=True)
    religion = Column(String(100), nullable=True)
    citizenship = Column(String(100), nullable=True)
    height = Column(String(50), nullable=True)
    weight = Column(String(50), nullable=True)
    language = Column(String(100), nullable=True)
    contact_number = Column(String(50), nullable=True)
    current_address = Column(String(255), nullable=True)
    provincial_address = Column(String(255), nullable=True)

    employee = relationship("Employee", back_populates="personal_details")
