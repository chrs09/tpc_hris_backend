from sqlalchemy import Column, Integer, String, Date, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from app.core.database import Base


class ApplicantEmploymentHistory(Base):
    __tablename__ = "tpc_applicant_employment_history"

    id = Column(Integer, primary_key=True, index=True)
    applicant_id = Column(Integer, ForeignKey("tpc_applicants.id"), nullable=False)

    company_name = Column(String(255), nullable=True)
    position = Column(String(150), nullable=True)
    date_from = Column(Date, nullable=True)
    date_to = Column(Date, nullable=True)

    reason_for_leaving = Column(String(255), nullable=True)
    salary_history = Column(Numeric(12, 2), nullable=True)
    salary_type = Column(String(50), nullable=True)

    applicant = relationship("Applicant", back_populates="employment_history")
