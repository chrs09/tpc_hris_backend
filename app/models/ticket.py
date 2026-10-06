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

    # Null for tickets filed on the public support form.
    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    # Who handles it: picked by the creator (any active user), else the
    # least-busy person in the category's Org Chart unit.
    assigned_to_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    # What it's about -> which Org Chart unit handles it.
    category_id = Column(Integer, ForeignKey("tpc_ticket_categories.id"), nullable=True)
    # "internal" (staff) or "public" (support form, no login).
    source = Column(String(10), nullable=False, default="internal")
    # Public requester (customer / store): how to reach them.
    requester_name = Column(String(150), nullable=True)
    requester_phone = Column(String(50), nullable=True)
    requester_email = Column(String(150), nullable=True)
    requester_company = Column(String(150), nullable=True)
    requester_ip = Column(String(64), nullable=True)
    # Timeline JSON: [{"action", "by", "at", "note", ...}] -- created,
    # assigned, forwarded, status changes.
    history = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = relationship("User", foreign_keys=[created_by_user_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id])
    category = relationship("TicketCategory")
