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
    # time_out/computed_hours are only known once the employee clocks out --
    # a request is created at clock-in time with both still null, so the
    # head can already see it (per the "view but can't approve yet" rule).
    time_out = Column(Time, nullable=True)
    computed_hours = Column(Float, nullable=True)

    reason = Column(Text, nullable=False)

    # Live selfie taken at clock-in -- proof the employee was actually
    # present when the callback OT started.
    selfie_photo_url = Column(String(500), nullable=True)

    # Location is best-effort only (never required/enforced, unlike trip
    # GPS) -- captured when the browser/device grants permission, stored
    # here for the record and also burned into the selfie's watermark.
    clock_in_lat = Column(Float, nullable=True)
    clock_in_long = Column(Float, nullable=True)
    clock_out_lat = Column(Float, nullable=True)
    clock_out_long = Column(Float, nullable=True)

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
