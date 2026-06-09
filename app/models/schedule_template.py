from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Time,
    DateTime,
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
