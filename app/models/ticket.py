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

    # Human-friendly reference for tracking, e.g. "TKT-2026-0001"
    # (sequential per year, see app/api/tickets.py).
    ticket_no = Column(String(20), unique=True, index=True, nullable=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Kanban column: "todo" | "in_progress" | "review" | "done"
    status = Column(String(20), nullable=False, default="todo")

    # "low" | "medium" | "high" -- nullable, not every ticket needs one.
    priority = Column(String(10), nullable=True)

    # Optional screenshot/reference image, uploaded separately via
    # POST /tickets/{id}/image (see app/api/tickets.py).
    image_url = Column(String(500), nullable=True)

    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)
    # Who handles it: always an IT employee (Employee.position "IT"),
    # assigned automatically on create -- never the creator. Null only
    # if no IT employee exists yet.
    assigned_to_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = relationship("User", foreign_keys=[created_by_user_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id])
