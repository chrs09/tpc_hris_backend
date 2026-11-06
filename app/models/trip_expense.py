from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class TripExpense(Base):
    """A driver's trip money (Approvals -> Trip Expenses; app/api/trip_expenses.py).

    kind "budget" -- money first, then liquidate (e.g. an offshore trip's
    shipping check + port / road cash):
        pending_approval (Org Chart heads, "Trip Expenses") -> for_release
        (Finance) -> released (driver liquidates: actual expenses +
        receipts) -> for_review -> completed; the reviewer can return it
        (returned -> driver fixes -> for_review). Unspent cash: returned in
        cash, or a payroll deduction (a "liquidation" TripCharge, so it
        goes through the trip charge payroll deductions). Overspent:
        reimbursed with payroll.
    kind "report" -- spent first, then reimbursed (e.g. parts the driver
    paid for): draft (adding expenses + receipts) -> for_review ->
    completed (allowed total reimbursed with payroll) / returned.

    Either can be rejected (with a reason) or cancelled by the driver
    before anything is released / reviewed.

    Reimbursements are paid with the payroll whose cutoff contains
    `reimburse_payroll_date` -- a separate line after net pay, like
    incentives.
    """

    __tablename__ = "tpc_trip_expenses"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(10), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)

    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=False, index=True)
    # The driver's login (null when office filed for someone without one).
    user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True, index=True)
    filed_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    # Budget: required. Report: optional (a trip and/or a unit, or neither).
    trip_id = Column(Integer, ForeignKey("tpc_trips.id"), nullable=True, index=True)
    vehicle_unit_id = Column(Integer, ForeignKey("tpc_vehicle_units.id"), nullable=True)
    purpose = Column(Text, nullable=True)

    # Org Chart approval (budget only): head user ids in order, whose turn
    # it is, and the approve / reject log.
    approval_chain = Column(Text, nullable=True)
    approval_step = Column(Integer, nullable=False, default=0)
    approval_log = Column(Text, nullable=True)

    # Release (budget): check / cash from Finance.
    released_amount = Column(Numeric(12, 2), nullable=True)
    release_method = Column(String(10), nullable=True)  # check / cash
    release_reference = Column(String(100), nullable=True)
    release_photo_url = Column(String(1000), nullable=True)
    released_at = Column(DateTime, nullable=True)
    released_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    submitted_at = Column(DateTime, nullable=True)

    # Review (liquidation / report) and how it was settled.
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    review_note = Column(Text, nullable=True)
    allowed_total = Column(Numeric(12, 2), nullable=True)
    # Unspent cash the driver owes (budget) and how: returned_cash / payroll.
    short_amount = Column(Numeric(12, 2), nullable=True)
    short_settlement = Column(String(20), nullable=True)
    trip_charge_id = Column(Integer, ForeignKey("tpc_trip_charges.id"), nullable=True)
    # Paid back to the driver with payroll.
    reimburse_amount = Column(Numeric(12, 2), nullable=True)
    reimburse_payroll_date = Column(Date, nullable=True, index=True)

    # Returned / rejected reason, or cancel note.
    note = Column(Text, nullable=True)
    # JSON list of {action, by, at, note}.
    history = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    employee = relationship("Employee")
    user = relationship("User", foreign_keys=[user_id])
    filed_by = relationship("User", foreign_keys=[filed_by_user_id])
    released_by = relationship("User", foreign_keys=[released_by_user_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_user_id])
    trip = relationship("Trip")
    lines = relationship(
        "TripExpenseLine",
        back_populates="expense",
        cascade="all, delete-orphan",
        order_by="TripExpenseLine.id",
    )


class TripExpenseLine(Base):
    """One expense line. stage "request": a budget's requested amount;
    stage "actual": what was really spent (the liquidation, or a report's
    expense), with its receipt and the reviewer's allowed amount."""

    __tablename__ = "tpc_trip_expense_lines"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(
        Integer, ForeignKey("tpc_trip_expenses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage = Column(String(10), nullable=False, default="actual")
    category = Column(String(40), nullable=False)
    description = Column(String(500), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False, default=0)
    expense_date = Column(Date, nullable=True)
    receipt_url = Column(String(1000), nullable=True)
    # Reviewer: allowed amount (0 = disallowed) and why.
    allowed_amount = Column(Numeric(12, 2), nullable=True)
    review_note = Column(String(500), nullable=True)

    expense = relationship("TripExpense", back_populates="lines")
