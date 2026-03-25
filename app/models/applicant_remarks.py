from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from datetime import datetime
from app.core.database import Base

class ApplicantRemark(Base):
    __tablename__ = "tpc_applicant_remarks"

    id = Column(Integer, primary_key=True, index=True)
    applicant_id = Column(Integer, ForeignKey("tpc_applicants.id"), nullable=False)
    status = Column(String(50), nullable=True)  # optional snapshot of status during remark
    remark = Column(Text, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)