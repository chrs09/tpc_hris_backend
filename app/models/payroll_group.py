from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.core.database import Base


class PayrollGroup(Base):
    """A payroll group: departments paid by the same rule and cutoff, so
    one payroll covers them all (e.g. "Driver - per trip - weekly" =
    Dumptruck + WingvanDriver). Set on the Payroll Groups page.

    pay_basis:
      "fixed_monthly"   -- monthly basic + allowance
      "fixed_daily"     -- daily rate x days worked
      "per_trip_driver" -- trip rates, driver 1st / next trip
      "per_trip_helper" -- trip rates, helper 1st / next trip

    departments: JSON list of department names in the group.
    payroll_type: "Monthly" / "Daily" to take only employees on that
    payroll type (Admin is split this way); None = everyone in the
    departments.

    The group's cutoff is the PayrollCutoffRule row named after the group,
    and its payroll status / saved figures use the group name in the
    PayrollRun / PayrollDeduction "department" column. Payrolls from
    before groups keep their department name there.
    """

    __tablename__ = "tpc_payroll_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True, index=True)
    pay_basis = Column(String(20), nullable=False, default="fixed_daily")
    departments = Column(Text, nullable=False, default="[]")
    payroll_type = Column(String(20), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    updated_by_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
