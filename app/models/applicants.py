from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.core.database import Base


class Applicant(Base):
    __tablename__ = "tpc_applicants"

    id = Column(Integer, primary_key=True, index=True)

    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(150))
    contact_number = Column(String(30))
    position_applied = Column(String(150))

    # cv_file = Column(String)

    status = Column(String(50), default="pending")  # pending, reviewed, hired, rejected

    created_at = Column(DateTime, default=datetime.utcnow)
