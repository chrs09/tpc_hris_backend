from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class ApplicantEducation(Base):
    __tablename__ = "tpc_applicant_education"

    id = Column(Integer, primary_key=True, index=True)
    applicant_id = Column(Integer, ForeignKey("tpc_applicants.id"), nullable=False)

    level = Column(String(100), nullable=True)
    institution = Column(String(255), nullable=True)
    degree = Column(String(255), nullable=True)
    year_from = Column(String(20), nullable=True)
    year_to = Column(String(20), nullable=True)
    skills = Column(String(255), nullable=True)

    applicant = relationship("Applicant", back_populates="education_records")
