from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Time,
    DateTime,
    Boolean,
)

from sqlalchemy.orm import relationship

from app.core.database import Base


class ScheduleTemplate(Base):
    __tablename__ = "tpc_schedule_templates"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    name = Column(
        String(100),
        nullable=False,
        unique=True,
    )

    description = Column(
        String(255),
        nullable=True,
    )

    monday_in = Column(Time, nullable=True)
    monday_out = Column(Time, nullable=True)

    tuesday_in = Column(Time, nullable=True)
    tuesday_out = Column(Time, nullable=True)

    wednesday_in = Column(Time, nullable=True)
    wednesday_out = Column(Time, nullable=True)

    thursday_in = Column(Time, nullable=True)
    thursday_out = Column(Time, nullable=True)

    friday_in = Column(Time, nullable=True)
    friday_out = Column(Time, nullable=True)

    saturday_in = Column(Time, nullable=True)
    saturday_out = Column(Time, nullable=True)

    sunday_in = Column(Time, nullable=True)
    sunday_out = Column(Time, nullable=True)

    # Trip-based schedule (drivers / helpers): no clock times, just which
    # days are work days ("mon,tue,...,sat"); the rest are rest days. A
    # trip on a rest day gets the rest-day premium in payroll.
    is_trip_based = Column(Boolean, nullable=False, default=False, server_default="0")
    work_days = Column(String(40), nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    employees = relationship(
        "Employee",
        back_populates="schedule_template",
    )
