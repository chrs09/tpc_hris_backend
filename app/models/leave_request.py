from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class LeaveRequest(Base):
    __tablename__ = "tpc_leave_requests"

    id = Column(Integer, primary_key=True, index=True)

    # The filer is always a User (every logged-in account has one), so
    # user_id is the anchor for identity/ownership checks. employee_id is
    # nullable because some admin accounts are pure system logins with no
    # linked HR employee record, but admins can still file leave.
    user_id = Column(
        Integer,
        ForeignKey("tpc_users.id"),
        nullable=False,
    )

    employee_id = Column(
        Integer,
        ForeignKey("tpc_employees.id"),
        nullable=True,
    )

    # "unpaid" is the only supported type for now; kept as a plain string
    # column so additional leave types can be added later without a migration.
    leave_type = Column(String(30), nullable=False, default="unpaid")

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    reason = Column(Text, nullable=False)

    status = Column(String(20), nullable=False, default="pending")
    # pending / approved / rejected / cancelled

    review_remarks = Column(Text, nullable=True)

    reviewed_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    employee = relationship(
        "Employee",
        back_populates="leave_requests",
    )

    requester = relationship(
        "User",
        foreign_keys=[user_id],
    )

    reviewed_by = relationship(
        "User",
        foreign_keys=[reviewed_by_user_id],
    )
