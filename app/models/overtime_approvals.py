from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    Date,
    DateTime,
    ForeignKey,
)

from sqlalchemy.orm import relationship

from app.core.database import Base


class OvertimeApproval(Base):
    __tablename__ = "tpc_overtime_approvals"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    employee_id = Column(
        Integer,
        ForeignKey("tpc_employees.id"),
        nullable=False,
    )

    cutoff_start = Column(
        Date,
        nullable=False,
    )

    cutoff_end = Column(
        Date,
        nullable=False,
    )

    detected_ot_hours = Column(
        Float,
        nullable=False,
        default=0,
    )

    approved_ot_hours = Column(
        Float,
        nullable=False,
        default=0,
    )

    status = Column(
        String(20),
        nullable=False,
        default="Pending",
    )
    # Pending
    # Approved
    # Reversed

    remarks = Column(
        String(500),
        nullable=True,
    )

    approved_by_user_id = Column(
        Integer,
        ForeignKey("tpc_users.id"),
        nullable=True,
    )

    approved_at = Column(
        DateTime,
        nullable=True,
    )

    reversed_by_user_id = Column(
        Integer,
        ForeignKey("tpc_users.id"),
        nullable=True,
    )

    reversed_at = Column(
        DateTime,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    employee = relationship(
        "Employee",
        back_populates="overtime_approvals",
    )

    approved_by = relationship(
        "User",
        foreign_keys=[approved_by_user_id],
    )

    reversed_by = relationship(
        "User",
        foreign_keys=[reversed_by_user_id],
    )

    details = relationship(
        "OvertimeApprovalDetail",
        back_populates="overtime_approval",
        cascade="all, delete-orphan",
    )