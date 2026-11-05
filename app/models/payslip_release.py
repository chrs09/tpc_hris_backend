from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT

from app.core.database import Base


class PayslipRelease(Base):
    """A payslip released to the employee (Payroll -> Release Payslip,
    only once the payroll is Locked / Paid). `snapshot` is the payslip
    exactly as Payroll had it (the PayslipModal row + period, JSON), so
    the employee sees what was approved even if data changes later.

    One per employee per payroll (department = the payroll group, or the
    department for payrolls from before groups) per Work History part
    (segment, "" = whole cutoff). Unlocking the payroll takes its
    releases back (app/api/payroll/payroll_runs.py)."""

    __tablename__ = "tpc_payslip_releases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, nullable=False, index=True)
    department = Column(String(50), nullable=False)
    cutoff_period = Column(String(50), nullable=False, index=True)
    segment = Column(String(20), nullable=False, default="", server_default="")
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    payout_date = Column(String(20), nullable=True)

    gross_pay = Column(Numeric(12, 2), nullable=False, default=0)
    net_pay = Column(Numeric(12, 2), nullable=False, default=0)
    snapshot = Column(Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=False)

    released_at = Column(DateTime, server_default=func.now(), nullable=False)
    released_by = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "department",
            "cutoff_period",
            "segment",
            name="uq_payslip_release_emp_payroll",
        ),
    )
