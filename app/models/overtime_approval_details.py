from sqlalchemy import (
    Column,
    Integer,
    Float,
    ForeignKey,
)

from sqlalchemy.orm import relationship

from app.core.database import Base


class OvertimeApprovalDetail(Base):
    __tablename__ = "tpc_overtime_approval_details"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    overtime_approval_id = Column(
        Integer,
        ForeignKey("tpc_overtime_approvals.id"),
        nullable=False,
    )

    attendance_id = Column(
        Integer,
        ForeignKey("tpc_attendance_records.id"),
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

    overtime_approval = relationship(
        "OvertimeApproval",
        back_populates="details",
    )

    attendance = relationship(
        "AttendanceRecord",
        back_populates="overtime_approval_details",
    )
