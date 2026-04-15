from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class ApplicantQuestion(Base):
    __tablename__ = "tpc_applicant_questions"

    id = Column(Integer, primary_key=True, index=True)
    target_role = Column(String(50), nullable=False, index=True)
    question_key = Column(String(100), unique=True, nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(50), nullable=False)  # text, textarea, select, date
    is_required = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    created_by_user = relationship("User")
