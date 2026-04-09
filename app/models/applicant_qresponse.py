from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from app.core.database import Base


class ApplicantQResponse(Base):
    __tablename__ = "tpc_applicant_qresponses"

    id = Column(Integer, primary_key=True, index=True)
    applicant_id = Column(
        Integer,
        ForeignKey("tpc_applicants.id"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        Integer,
        ForeignKey("tpc_applicant_questions.id"),
        nullable=False,
        index=True,
    )
    answer_text = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    applicant_id = Column(Integer, ForeignKey("tpc_applicants.id"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("tpc_applicant_questions.id"), nullable=False, index=True)