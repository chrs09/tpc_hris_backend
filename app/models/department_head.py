from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class DepartmentHead(Base):
    """Reporting hierarchy: which user is the immediate head of a given
    employee department (e.g. Motorpool -> Marjorie, Admin -> superadmin).
    One row per department; every employee in that department shares the
    same head."""

    __tablename__ = "tpc_department_heads"

    id = Column(Integer, primary_key=True, index=True)

    department = Column(String(50), nullable=False, unique=True, index=True)

    head_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)

    updated_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    head_user = relationship("User", foreign_keys=[head_user_id])
    updated_by = relationship("User", foreign_keys=[updated_by_user_id])
