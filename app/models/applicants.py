from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.core.database import Base


class Applicant(Base):
    __tablename__ = "tpc_applicants"

    id = Column(Integer, primary_key=True, index=True)

    first_name = Column(String)
    last_name = Column(String)
    email = Column(String)
    contact_number = Column(String)
    position_applied = Column(String)

    cv_file = Column(String)

    status = Column(String, default="pending")  # pending, reviewed, hired, rejected

    created_at = Column(DateTime, default=datetime.utcnow)