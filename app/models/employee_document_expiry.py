from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.core.database import Base


class EmployeeDocumentExpiry(Base):
    """Expiry of one 201 Employment File (e.g. LICENSE, NC3) of an employee.

    has_expiry: HR's flag that this document expires. With no row, the
    default comes from app/services/employee_documents.py
    (EXPIRING_BY_DEFAULT). expiry_date drives the HR Dashboard's
    "Nearing expiry" list."""

    __tablename__ = "tpc_employee_document_expiries"
    __table_args__ = (
        UniqueConstraint("employee_id", "document_type", name="uq_employee_document_expiry"),
    )

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("tpc_employees.id"), nullable=False, index=True)
    document_type = Column(String(50), nullable=False)
    has_expiry = Column(Boolean, nullable=False, default=True, server_default="1")
    expiry_date = Column(Date, nullable=True)
    updated_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
