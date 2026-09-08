from datetime import datetime

from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class OvertimeApprover(Base):
    """Roster of users who can be selected as the designated approver when
    an employee files a callback overtime request. Membership here is
    independent of system role, since the person who calls someone in for
    overtime (e.g. a department head) isn't necessarily an admin login."""

    __tablename__ = "tpc_overtime_approvers"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("tpc_users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    is_active = Column(Boolean, nullable=False, default=True)

    added_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", foreign_keys=[user_id])
    added_by = relationship("User", foreign_keys=[added_by_user_id])
