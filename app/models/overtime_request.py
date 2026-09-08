from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    Time,
    DateTime,
    Float,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class OvertimeRequest(Base):
    """An employee-initiated callback overtime request -- e.g. clocked out
    at 5pm, then called back in at 8pm. Distinct from OvertimeApproval
    (tpc_overtime_approvals), which tracks OT detected from attendance for
    a payroll cutoff; an approved OvertimeRequest's hours get merged into
    the matching OvertimeApproval row so payroll keeps a single OT source
    of truth per employee per cutoff."""

    __tablename__ = "tpc_overtime_requests"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=True)

    requested_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)

    ot_date = Column(Date, nullable=False)
    time_in = Column(Time, nullable=False)
    time_out = Column(Time, nullable=False)
    computed_hours = Column(Float, nullable=False)

    reason = Column(Text, nullable=False)

    status = Column(String(20), nullable=False, default="pending")
    # pending / approved / rejected / cancelled

    approved_hours = Column(Float, nullable=True)
    remarks = Column(Text, nullable=True)

    approved_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    overtime_approval_id = Column(
        Integer, ForeignKey("tpc_overtime_approvals.id"), nullable=True
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    employee = relationship("Employee", foreign_keys=[employee_id])
    requester = relationship("User", foreign_keys=[user_id])
    requested_by = relationship("User", foreign_keys=[requested_by_user_id])
    approved_by = relationship("User", foreign_keys=[approved_by_user_id])
    overtime_approval = relationship("OvertimeApproval", foreign_keys=[overtime_approval_id])
