from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    ForeignKey,
)

from sqlalchemy.orm import relationship

from app.core.database import Base


class DispatchHelper(Base):
    __tablename__ = "tpc_dispatch_helpers"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    dispatch_item_id = Column(
        Integer,
        ForeignKey(
            "tpc_dispatch_items.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    helper_id = Column(
        Integer,
        ForeignKey(
            "tpc_employees.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # ============================
    # Relationships
    # ============================

    dispatch_item = relationship(
        "DispatchItem",
        back_populates="helpers",
    )

    helper = relationship(
        "Employee",
        back_populates="dispatch_assignments",
    )