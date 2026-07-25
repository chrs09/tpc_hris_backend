import enum

from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    ForeignKey,
    Enum,
    String,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class FinanceReviewStatus(str, enum.Enum):
    OFFICE_REVIEW = "office_review"
    FINANCE_REVIEW = "finance_review"
    APPROVED = "approved"


class TripFinanceReview(Base):
    """
    One review record per trip.

    Review flow:

    Coordinator
        ↓
    Office Personnel
        ↓
    Finance
        ↓
    Payroll
    """

    __tablename__ = "tpc_trip_finance_reviews"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    trip_id = Column(
        Integer,
        ForeignKey(
            "tpc_trips.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    # =====================================================
    # COORDINATOR REVIEW
    # =====================================================

    coordinator_id = Column(
        Integer,
        ForeignKey("tpc_users.id"),
        nullable=False,
    )

    coordinator_remarks = Column(
        String(1000),
        nullable=False,
    )

    # Business settlement date.
    # This will later determine payroll cutoff.
    coordinator_settlement_date = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    # System timestamp when review record was created.
    submitted_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    # =====================================================
    # CURRENT REVIEW STAGE
    # =====================================================

    status = Column(
        Enum(
            FinanceReviewStatus,
            name="finance_review_status_enum",
            values_callable=lambda enum_cls: [
                e.value for e in enum_cls
            ],
        ),
        default=FinanceReviewStatus.OFFICE_REVIEW,
        nullable=False,
        index=True,
    )

    # =====================================================
    # OFFICE PERSONNEL REVIEW
    # =====================================================

    office_reviewer_id = Column(
        Integer,
        ForeignKey("tpc_users.id"),
        nullable=True,
    )

    office_remarks = Column(
        String(1000),
        nullable=True,
    )

    office_reviewed_at = Column(
        DateTime,
        nullable=True,
    )

    # =====================================================
    # FINANCE REVIEW
    # =====================================================

    finance_reviewer_id = Column(
        Integer,
        ForeignKey("tpc_users.id"),
        nullable=True,
    )

    approved_at = Column(
        DateTime,
        nullable=True,
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    trip = relationship(
        "Trip",
        back_populates="finance_review",
    )

    coordinator = relationship(
        "User",
        foreign_keys=[coordinator_id],
    )

    office_reviewer = relationship(
        "User",
        foreign_keys=[office_reviewer_id],
    )

    finance_reviewer = relationship(
        "User",
        foreign_keys=[finance_reviewer_id],
    )