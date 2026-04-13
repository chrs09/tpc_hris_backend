from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class ApplicantOnboarding(Base):
    __tablename__ = "tpc_applicant_onboarding"

    id = Column(Integer, primary_key=True, index=True)
    applicant_id = Column(
        Integer, ForeignKey("tpc_applicants.id"), unique=True, nullable=False
    )

    # basic
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    email = Column(String(150), nullable=True)
    department = Column(String(100), nullable=True)
    position = Column(String(150), nullable=True)
    date_hired = Column(Date, nullable=True)

    # personal
    birthday = Column(Date, nullable=True)
    birthplace = Column(String(150), nullable=True)
    gender = Column(String(50), nullable=True)
    civil_status = Column(String(50), nullable=True)
    religion = Column(String(100), nullable=True)
    citizenship = Column(String(100), nullable=True)
    height = Column(String(50), nullable=True)
    weight = Column(String(50), nullable=True)
    language = Column(String(100), nullable=True)
    contact_number = Column(String(50), nullable=True)
    current_address = Column(String(255), nullable=True)
    provincial_address = Column(String(255), nullable=True)

    # family
    spouse_name = Column(String(150), nullable=True)
    father_name = Column(String(150), nullable=True)
    mother_name = Column(String(150), nullable=True)

    # emergency
    emergency_contact_name = Column(String(150), nullable=True)
    emergency_contact_number = Column(String(50), nullable=True)
    emergency_relationship = Column(String(100), nullable=True)

    # salary
    current_salary = Column(Numeric(12, 2), nullable=True)
    expected_salary = Column(Numeric(12, 2), nullable=True)
    salary_type = Column(String(50), nullable=True)

    # government
    sss = Column(String(50), nullable=True)
    philhealth = Column(String(50), nullable=True)
    pagibig = Column(String(50), nullable=True)
    tin = Column(String(50), nullable=True)

    # submission tracking
    is_submitted = Column(Integer, default=0)
    submitted_at = Column(DateTime, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    applicant = relationship("Applicant", back_populates="onboarding")