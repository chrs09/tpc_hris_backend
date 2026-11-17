from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class RoleModuleDefault(Base):
    """The modules a role gets by default (Administrator -> Role Access).

    One row per configured role. Everyone with that role who has no
    custom access of their own (Employee.has_custom_module_access False)
    follows it -- including people added later. A role with no row keeps
    the built-in defaults from the code (the `roles` lists on each page /
    endpoint). See app/services/role_defaults.py."""

    __tablename__ = "tpc_role_module_defaults"

    role = Column(String(50), primary_key=True)
    # JSON lists of module keys (same keys as EmployeeModuleAccess).
    module_keys = Column(Text, nullable=False, default="[]")
    # Of those, the view-only ones ("Can edit: No").
    read_only_keys = Column(Text, nullable=False, default="[]")

    updated_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
