from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class IncentiveProgram(Base):
    """One incentive program for a period, set on the Incentive Policies
    page instead of hard-coded -- management changes the amounts every
    month (memo 26-005 Tier 3 was 2,000, 26-006 made it 3,000), so a new
    month is a copied row, not a code change.

    rule_type (amounts / options live in `settings`, JSON -- see
    app/services/incentives.py RULE_TYPES for each type's settings):
      "trip_tiers"          -- completed trips in the period reach a tier
                               (65 / 52 / 39 trips); highest tier only.
      "daily_cash"          -- cash per trip in a day (Mon-Sat), e.g. the
                               2nd trip or a first trip before 6am; paid
                               by the coordinator.
      "long_distance"       -- per trip by the km range of its farthest
                               destination; driver gets the helper base
                               plus an extra.
      "complete_attendance" -- no absences in the period earns a % bonus.

    applies_to: "drivers", "helpers" or "drivers,helpers".
    """

    __tablename__ = "tpc_incentive_programs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    memo_no = Column(String(30), nullable=True)
    rule_type = Column(String(30), nullable=False, index=True)
    applies_to = Column(String(50), nullable=False, default="drivers")

    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False)
    release_date = Column(Date, nullable=True)

    settings = Column(Text, nullable=False, default="{}")
    is_active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)

    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    updated_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
