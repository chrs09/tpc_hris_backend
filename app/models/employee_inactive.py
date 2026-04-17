from datetime import datetime

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class EmployeeInactiveRecord(Base):
    __tablename__ = "tpc_employee_inactive_records"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        Integer,
        ForeignKey("tpc_employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    inactive_reason = Column(String(100), nullable=False)
    inactive_date = Column(Date, nullable=False)
    inactive_remarks = Column(Text, nullable=True)

    created_by_user_id = Column(
        Integer,
        ForeignKey("tpc_users.id"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    reactivated_at = Column(DateTime, nullable=True)
    reactivated_by_user_id = Column(
        Integer,
        ForeignKey("tpc_users.id"),
        nullable=True,
    )

    employee = relationship("Employee", back_populates="inactive_records")
    created_by_user = relationship(
        "User",
        foreign_keys=[created_by_user_id],
    )
    reactivated_by_user = relationship(
        "User",
        foreign_keys=[reactivated_by_user_id],
    )
