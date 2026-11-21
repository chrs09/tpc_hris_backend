"""SSS / Pag-IBIG loans paid by payroll (Finance -> Loan Amortization).

A loan has the amount borrowed, the monthly amortization and the number
of months to pay. Payroll deducts the amortization every month (split
across the two cutoffs, or on one of them) until monthly amortization x
terms is paid. Each deduction is an EmployeeLoanPayment tagged with the
cutoff, so regenerating a cutoff replaces its payment instead of
deducting twice (same idea as cash advances).
"""

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, func

from app.core.database import Base

LOAN_TYPES = ("SSS", "PAGIBIG")
# When in the month the amortization is taken.
SCHEDULES = ("SPLIT", "FIRST", "SECOND")
STATUSES = ("ACTIVE", "CANCELLED")


class EmployeeLoan(Base):
    __tablename__ = "tpc_employee_loans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, nullable=False, index=True)
    loan_type = Column(String(20), nullable=False)  # SSS | PAGIBIG
    reference_no = Column(String(60), nullable=True)
    loan_amount = Column(Numeric(12, 2), nullable=False)
    monthly_amortization = Column(Numeric(12, 2), nullable=False)
    terms_months = Column(Integer, nullable=False)
    # First month payroll deducts (day is ignored).
    start_date = Column(Date, nullable=False)
    deduct_schedule = Column(String(10), nullable=False, default="SPLIT", server_default="SPLIT")
    # Paid before this system took over (an existing loan).
    opening_paid = Column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    status = Column(String(12), nullable=False, default="ACTIVE", server_default="ACTIVE")
    notes = Column(String(300), nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class EmployeeLoanPayment(Base):
    __tablename__ = "tpc_employee_loan_payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(Integer, ForeignKey("tpc_employee_loans.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    # Set for payroll deductions ("2026-11-01_2026-11-15"); null = recorded by hand.
    cutoff_period = Column(String(50), nullable=True, index=True)
    note = Column(String(200), nullable=True)
    recorded_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
