from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.user import User


class Employee(Base):
    __tablename__ = "tpc_employees"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    position = Column(String(100), nullable=False)
    date_hired = Column(Date, nullable=False)
    department = Column(String(100), nullable=False)
    is_active = Column(Integer, nullable=False, default=1)
    is_available = Column(Integer, nullable=False, default=1)

    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)
    updated_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 1️⃣ One-to-one: employee may have login
    user = relationship(
        "User",
        foreign_keys=[User.employee_id],
        back_populates="employee",
        uselist=False,
    )

    # 2️⃣ Many employees created by one user
    created_by_user = relationship(
        "User", foreign_keys=[created_by_user_id], back_populates="created_employees"
    )

    updated_by_user = relationship(
        "User", foreign_keys=[updated_by_user_id], back_populates="updated_employees"
    )

    # 3️⃣ Attendance records
    attendance_records = relationship("AttendanceRecord", back_populates="employee")

    trip_assignments = relationship(
        "TripHelper", back_populates="helper", cascade="all, delete-orphan"
    )

    trips = relationship("Trip", secondary="tpc_trip_helpers", viewonly=True)

    # Extended HRIS relationships
    personal_details = relationship(
        "EmployeePersonalDetails",
        back_populates="employee",
        uselist=False,
        cascade="all, delete-orphan",
    )

    family_details = relationship(
        "EmployeeFamilyDetails",
        back_populates="employee",
        uselist=False,
        cascade="all, delete-orphan",
    )

    government_details = relationship(
        "EmployeeGovernmentDetails",
        back_populates="employee",
        uselist=False,
        cascade="all, delete-orphan",
    )

    emergency_contacts = relationship(
        "EmployeeEmergencyContact",
        back_populates="employee",
        cascade="all, delete-orphan",
    )

    education_records = relationship(
        "EmployeeEducation", back_populates="employee", cascade="all, delete-orphan"
    )

    employment_history = relationship(
        "EmployeeEmploymentHistory",
        back_populates="employee",
        cascade="all, delete-orphan",
    )

    references = relationship(
        "EmployeeReference", back_populates="employee", cascade="all, delete-orphan"
    )

    documents = relationship(
        "EmployeeDocument", back_populates="employee", cascade="all, delete-orphan"
    )
