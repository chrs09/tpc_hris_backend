from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class Ticket(Base):
    """A lightweight Kanban-style change-request board -- superadmin logs
    what they want changed/fixed here (title + a clear description) so
    it's tracked in one place instead of scattered across chat, with a
    status any admin viewing the board can move as work progresses."""

    __tablename__ = "tpc_tickets"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Kanban column: "todo" | "in_progress" | "review" | "done"
    status = Column(String(20), nullable=False, default="todo")

    # "low" | "medium" | "high" -- nullable, not every ticket needs one.
    priority = Column(String(10), nullable=True)

    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)
    # Who's responsible for actually handling this ticket -- nullable,
    # not every ticket needs an owner right away.
    assigned_to_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = relationship("User", foreign_keys=[created_by_user_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id])
