from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class UserRevision(Base):
    """Audit trail for changes made to a user account (role, active status).

    Required by: update_user_service() in app/services/user_service.py --
    every time an admin changes a user's role or active status, one row is
    written here so the change is traceable later (who did it, when, what
    changed from/to, and why). Mirrors the existing
    tpc_employee_inactive_records pattern (see app/models/employee_inactive.py)
    but generalized to any tracked field instead of only inactive/reactive.
    """

    __tablename__ = "tpc_user_revisions"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("tpc_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    field_changed = Column(String(50), nullable=False)  # "role" or "is_active"
    old_value = Column(String(50), nullable=True)
    new_value = Column(String(50), nullable=True)

    # Required by the API when deactivating a user (is_active True -> False);
    # optional for other kinds of changes.
    reason = Column(Text, nullable=True)

    changed_by_user_id = Column(
        Integer,
        ForeignKey("tpc_users.id"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", foreign_keys=[user_id])
    changed_by_user = relationship("User", foreign_keys=[changed_by_user_id])
