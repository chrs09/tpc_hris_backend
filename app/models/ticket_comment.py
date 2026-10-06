from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class TicketComment(Base):
    """A comment/remark on a ticket -- the creator adds follow-ups or
    clarifications, IT replies (see app/api/tickets.py)."""

    __tablename__ = "tpc_ticket_comments"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(
        Integer, ForeignKey("tpc_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)
    body = Column(Text, nullable=False)
    # Sent to the public requester (emailed, shown on their status page).
    to_customer = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", foreign_keys=[user_id])
