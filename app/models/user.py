from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base


class User(Base):
    __tablename__ = "tpc_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    role = Column(String(12), default="employee")  # admin / employee
    is_active = Column(Boolean, default=True)
    # employee relationship
    employees = relationship(
        "Employee", back_populates="user", cascade="all, delete-orphan"
    )

    # Relationship to attendance records created by this user
    attendance_created_records = relationship(
        "AttendanceRecord", back_populates="checked_in_by", cascade="all, delete-orphan"
    )
