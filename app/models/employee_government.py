from sqlalchemy import Boolean, Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class EmployeeGovernmentDetails(Base):
    __tablename__ = "tpc_employee_government_details"

    id = Column(Integer, primary_key=True)
    employee_id = Column(
        Integer, ForeignKey("tpc_employees.id"), unique=True, nullable=False
    )

    sss_number = Column(String(50), nullable=True)
    philhealth_number = Column(String(50), nullable=True)
    pagibig_number = Column(String(50), nullable=True)
    tin_number = Column(String(50), nullable=True)

    # Which contributions payroll deducts for this employee (HRIS ->
    # Government Contributions). Unticked = not deducted. Started ticked
    # for Monthly-paid staff (what payroll did before these existed).
    has_sss = Column(Boolean, nullable=False, default=False, server_default="0")
    has_philhealth = Column(Boolean, nullable=False, default=False, server_default="0")
    has_pagibig = Column(Boolean, nullable=False, default=False, server_default="0")
    has_tax = Column(Boolean, nullable=False, default=False, server_default="0")

    employee = relationship("Employee", back_populates="government_details")
