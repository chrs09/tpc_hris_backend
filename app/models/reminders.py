from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, Text
from datetime import datetime
from sqlalchemy.orm import relationship
from app.core.database import Base


class Reminder(Base):
    __tablename__ = "tpc_reminders"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(Text, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"))
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    created_by_user = relationship("User", back_populates="created_reminders")