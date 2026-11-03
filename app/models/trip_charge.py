from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class TripCharge(Base):
    """A shortage or accident on a trip, and what personnel owe for it. It
    can be recorded at any time after the trip (Coca-Cola's shortage reports
    can come late), since what gets deducted goes to the next open payroll,
    not the trip's own cutoff.

    recorded -> for_explanation (people told, chance to explain) -> approved
    (deducted from payroll), or cancelled. "settled" is only shown, once
    every person's balance is zero."""

    __tablename__ = "tpc_trip_charges"

    id = Column(Integer, primary_key=True, index=True)

    # "shortage" or "accident"
    charge_type = Column(String(20), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="recorded", index=True)

    trip_id = Column(Integer, ForeignKey("tpc_trips.id"), nullable=False, index=True)
    incident_date = Column(Date, nullable=False)
    description = Column(Text, nullable=True)

    # Shortage: the cost of what's short. Accident: the total damage.
    total_amount = Column(Numeric(12, 2), nullable=False, default=0)

    # Shortage only
    shipment_no = Column(String(100), nullable=True)
    report_reference = Column(String(100), nullable=True)
    report_date = Column(Date, nullable=True)
    item = Column(String(255), nullable=True)
    quantity = Column(Numeric(10, 2), nullable=True)
    unit_cost = Column(Numeric(12, 2), nullable=True)

    # Accident only
    # "pending", "covered", "denied" or "not_claimed"
    insurance_status = Column(String(20), nullable=True)
    insurance_reference = Column(String(100), nullable=True)
    participation_amount = Column(Numeric(12, 2), nullable=True)
    # "pending", "negligent" or "not_negligent"
    investigation_result = Column(String(20), nullable=True)
    investigation_notes = Column(Text, nullable=True)

    # What personnel pay in total: the allocations add up to this. Differs
    # from the rule in suggested_chargeable only with a reason.
    chargeable_amount = Column(Numeric(12, 2), nullable=False, default=0)
    chargeable_reason = Column(Text, nullable=True)

    # JSON list of file urls (the report, photos, the insurer's letter).
    attachments = Column(Text, nullable=True)
    # JSON list of {action, by, by_name, at, note}, oldest first.
    history = Column(Text, nullable=True)

    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    approved_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    trip = relationship("Trip")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    approved_by = relationship("User", foreign_keys=[approved_by_user_id])
    allocations = relationship(
        "TripChargeAllocation",
        back_populates="charge",
        cascade="all, delete-orphan",
    )


class TripChargeAllocation(Base):
    """One person's share of a charge. Their balance is always amount minus
    SUM(deduction logs), never a stored number, same as a cash advance."""

    __tablename__ = "tpc_trip_charge_allocations"

    id = Column(Integer, primary_key=True, index=True)

    trip_charge_id = Column(
        Integer, ForeignKey("tpc_trip_charges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=False, index=True)

    amount = Column(Numeric(12, 2), nullable=False, default=0)
    # Most to deduct per cutoff; null = the whole balance at once.
    deduction_per_pay = Column(Numeric(12, 2), nullable=True)

    notified_at = Column(DateTime, nullable=True)
    explanation = Column(Text, nullable=True)

    charge = relationship("TripCharge", back_populates="allocations")
    employee = relationship("Employee")
    deduction_logs = relationship(
        "TripChargeDeductionLog",
        back_populates="allocation",
        cascade="all, delete-orphan",
    )


class TripChargeDeductionLog(Base):
    """One deduction from payroll. Regenerating a cutoff's payslip replaces
    that cutoff's entries instead of adding more."""

    __tablename__ = "tpc_trip_charge_deduction_logs"

    id = Column(Integer, primary_key=True, index=True)

    allocation_id = Column(
        Integer,
        ForeignKey("tpc_trip_charge_allocations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount = Column(Numeric(12, 2), nullable=False)
    payroll_cutoff_period = Column(String(50), nullable=False, index=True)

    recorded_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    allocation = relationship("TripChargeAllocation", back_populates="deduction_logs")
