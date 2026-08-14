from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    UniqueConstraint,
    func,
)

from app.core.database import Base


class PayrollDeduction(Base):
    """
    SSS / PhilHealth / Pag-IBIG / tardiness / undertime / absence
    deductions (plus gross/net pay, kept for reference) computed for one
    employee for one cutoff period.
    """

    __tablename__ = "payroll_deductions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Same format PayrollList.jsx already uses for its adjustment keys,
    # e.g. "2026-08-01_2026-08-15"
    cutoff_period = Column(String(50), nullable=False, index=True)

    employee_id = Column(Integer, nullable=False, index=True)

    # e.g. "motorpol", "admin"
    department = Column(String(50), nullable=False)

    gross_pay = Column(Numeric(12, 2), nullable=False, default=0)
    sss_deduction = Column(Numeric(12, 2), nullable=False, default=0)
    philhealth_deduction = Column(Numeric(12, 2), nullable=False, default=0)
    pagibig_deduction = Column(Numeric(12, 2), nullable=False, default=0)
    tardiness_deduction = Column(Numeric(12, 2), nullable=False, default=0)
    undertime_deduction = Column(Numeric(12, 2), nullable=False, default=0)
    absent_deduction = Column(Numeric(12, 2), nullable=False, default=0)
    net_pay = Column(Numeric(12, 2), nullable=False, default=0)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # One row per employee per cutoff — re-saving (e.g. clicking
        # Generate Payslip again) updates the row instead of duplicating it.
        UniqueConstraint(
            "employee_id",
            "cutoff_period",
            name="uq_payroll_deductions_emp_cutoff",
        ),
    )