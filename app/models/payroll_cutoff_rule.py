from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class PayrollCutoffRule(Base):
    """How one department (employee group) is paid -- set on the Payroll
    Cutoffs page instead of hard-coded, so a new group (e.g.
    WingvanDriver) only needs a row, not a code change.

    schedule_type:
      "semi_monthly" -- two cutoffs a month. The first runs
          first_start_day .. second_start_day - 1; the second runs
          second_start_day .. first_start_day - 1 of the next month (or
          to month end when first_start_day is 1). E.g. 1/16 = 1-15 and
          16-end; 11/26 = 11-25 and 26-10.
          Payout: first_payout_day of the month the first cutoff is in,
          second_payout_day of the month after the second cutoff starts
          (0 = last day of the month).
      "weekly" -- 7-day cutoffs starting on week_start_day (0 = Sunday ..
          6 = Saturday), paid payout_offset_days after the cutoff ends.
      "monthly" -- 1st to month end, paid on first_payout_day (0 = last
          day of the month).
    """

    __tablename__ = "tpc_payroll_cutoff_rules"

    id = Column(Integer, primary_key=True, index=True)
    department = Column(String(50), nullable=False, unique=True, index=True)
    schedule_type = Column(String(20), nullable=False, default="semi_monthly")

    first_start_day = Column(Integer, nullable=True)
    second_start_day = Column(Integer, nullable=True)
    first_payout_day = Column(Integer, nullable=True)
    second_payout_day = Column(Integer, nullable=True)

    week_start_day = Column(Integer, nullable=True)
    payout_offset_days = Column(Integer, nullable=True)

    updated_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
