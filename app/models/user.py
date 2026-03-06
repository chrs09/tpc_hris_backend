import enum
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.core.database import Base


# 🔐 Strict role definition (database enforced)
class UserRole(str, enum.Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    DRIVER = "driver"
    HELPER = "helper"
    EMPLOYEE = "employee"


class User(Base):
    __tablename__ = "tpc_users"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)

    hashed_password = Column(String(255), nullable=False)

    # 🔐 Enforced enum instead of String
    role = Column(
        Enum(UserRole, name="user_role_enum"), nullable=False, default=UserRole.EMPLOYEE
    )

    # One employee = one login max
    employee_id = Column(
        Integer,
        ForeignKey("tpc_employees.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )

    is_active = Column(Boolean, default=True, nullable=False)
    must_change_password = Column(Boolean, default=True, nullable=False)

    # =============================
    # RELATIONSHIPS
    # =============================

    # 1️⃣ One-to-one: user login belongs to one employee
    employee = relationship(
        "Employee", foreign_keys=[employee_id], back_populates="user", uselist=False
    )

    # 2️⃣ One-to-many: user (admin/superadmin) created many employees
    created_employees = relationship(
        "Employee",
        foreign_keys="Employee.created_by_user_id",
        back_populates="created_by_user",
    )

    # 3️⃣ One-to-many: user created many attendance records
    attendance_created_records = relationship(
        "AttendanceRecord",
        foreign_keys="AttendanceRecord.created_by_user_id",
        back_populates="checked_in_by",
    )

    # 4️⃣ One-to-many: driver has many trips
    trips = relationship("Trip", back_populates="driver", cascade="all, delete-orphan")
