from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class CashAdvanceRequest(Base):
    """An employee-initiated cash advance request. Mirrors OvertimeRequest's
    approval routing -- the approver is resolved from the filer's employee
    department via the Reporting Hierarchy (DepartmentHead), not manually
    picked and not based on role.

    Superadmin only configures the PER-PAY deduction amount options (see
    CashAdvanceDeductionOption) -- the total `amount` requested is typed
    freely by the driver. `deduction_per_pay_amount` is copied from the
    chosen option at filing time so the historical record stays stable
    even if the option is later edited or removed. The running balance is
    computed from `amount` minus the sum of CashAdvanceDeductionLog
    entries, rather than stored directly, to avoid drift."""

    __tablename__ = "tpc_cash_advance_requests"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=True)

    requested_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)

    # Total amount requested, typed freely by the driver.
    amount = Column(Numeric(10, 2), nullable=False)

    # The per-pay-period deduction amount, picked from a superadmin preset
    # (CashAdvanceDeductionOption) and copied here at filing time.
    deduction_option_id = Column(
        Integer,
        ForeignKey("tpc_cash_advance_deduction_options.id"),
        nullable=True,
    )
    deduction_per_pay_amount = Column(Numeric(10, 2), nullable=False)

    reason = Column(Text, nullable=False)

    # The driver must acknowledge the current CashAdvanceTerms content
    # before filing -- recorded here so there's a record they agreed to
    # it, and when.
    terms_accepted = Column(Boolean, nullable=False, default=False)
    terms_accepted_at = Column(DateTime, nullable=True)

    status = Column(String(20), nullable=False, default="pending")
    # pending / approved / rejected / cancelled

    remarks = Column(Text, nullable=True)

    approved_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    # The amount actually approved, which the approver may set lower than
    # `amount` (the driver's original request) -- e.g. requested ₱5,000,
    # approved only ₱3,000. Null until approved, at which point it's the
    # authoritative figure for balance/deduction math; `amount` always
    # stays the original request for display ("Requested Amount" vs
    # "Approved CA"). Defaults to the full requested amount if the
    # approver doesn't override it.
    approved_amount = Column(Numeric(10, 2), nullable=True)

    # Proof/reference that the approved funds were actually handed over
    # to the employee -- e.g. a GCash reference number, check number, or
    # payroll-release note. Separate from approval itself, since the
    # money isn't necessarily released the same moment it's approved.
    release_reference = Column(String(255), nullable=True)
    released_at = Column(DateTime, nullable=True)
    released_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    employee = relationship("Employee", foreign_keys=[employee_id])
    requester = relationship("User", foreign_keys=[user_id])
    requested_by = relationship("User", foreign_keys=[requested_by_user_id])
    approved_by = relationship("User", foreign_keys=[approved_by_user_id])
    released_by = relationship("User", foreign_keys=[released_by_user_id])
    deduction_option = relationship(
        "CashAdvanceDeductionOption", back_populates="requests"
    )
    deduction_logs = relationship(
        "CashAdvanceDeductionLog",
        back_populates="cash_advance_request",
        cascade="all, delete-orphan",
    )
