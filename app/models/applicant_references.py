from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class ApplicantReference(Base):
    __tablename__ = "tpc_applicant_references"

    id = Column(Integer, primary_key=True, index=True)
    applicant_id = Column(Integer, ForeignKey("tpc_applicants.id"), nullable=False)

    name = Column(String(150), nullable=True)
    position = Column(String(150), nullable=True)
    address = Column(String(255), nullable=True)
    contact = Column(String(100), nullable=True)

    applicant = relationship("Applicant", back_populates="references")
