from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class OrgUnit(Base):
    """A box on the organizational chart (e.g. Owner, Admins, HR, IT,
    Trip Management, Coordinator, Drivers). Units nest via parent_id to
    any depth. Members are resolved live from rules, so new hires land
    in the right box automatically -- an employee belongs to a unit if
    they match ANY of: listed positions, listed user roles, listed
    departments, or are pinned by employee id. All four are JSON lists
    of strings/ints. See app/api/department_head.py (org tree)."""

    __tablename__ = "tpc_org_units"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey("tpc_org_units.id"), nullable=True, index=True)
    # Extra units this one also reports to (JSON list of ids). The unit is
    # drawn once, under parent_id, and linked from these.
    also_reports_to = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    head_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    member_positions = Column(Text, nullable=True)
    member_roles = Column(Text, nullable=True)
    member_departments = Column(Text, nullable=True)
    member_employee_ids = Column(Text, nullable=True)

    updated_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    head_user = relationship("User", foreign_keys=[head_user_id])
