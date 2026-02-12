from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class Employee(Base):
    __tablename__ = "tpc_employees"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(50), unique=True, index=True, nullable=False)
    position = Column(String(100), nullable=False)
    date_hired = Column(Date, nullable=False)
    department = Column(String(100), nullable=False)
    is_active = Column(Integer, nullable=False, default=1)  # 1 for active, 0 for inactive
    created_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=False)

    user = relationship(
        "User", 
        back_populates="employees"
    )