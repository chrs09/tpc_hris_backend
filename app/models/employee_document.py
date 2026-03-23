from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class EmployeeDocument(Base):
    __tablename__ = "tpc_employee_documents"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=False)

    document_type = Column(String(100), nullable=True)
    file_path = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    employee = relationship("Employee", back_populates="documents")