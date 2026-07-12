# app/models/dispatch.py

from datetime import datetime
import enum

from sqlalchemy import (
    Column,
    Integer,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    func,
)

from sqlalchemy.orm import relationship

from app.core.database import Base


class DispatchStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ASSIGNED = "ASSIGNED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Dispatch(Base):
    __tablename__ = "tpc_dispatches"

    id = Column(Integer, primary_key=True, index=True)

    plan_date = Column(
        Date,
        nullable=False,
        index=True,
    )

    status = Column(
        Enum(
            DispatchStatus,
            name="dispatch_status_enum",
        ),
        nullable=False,
        default=DispatchStatus.DRAFT,
    )

    created_by = Column(
        Integer,
        ForeignKey("tpc_users.id"),
        nullable=False,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=datetime.utcnow,
    )

    items = relationship(
        "DispatchItem",
        back_populates="dispatch",
        cascade="all, delete-orphan",
    )

    creator = relationship(
        "User",
        foreign_keys=[created_by],
    )