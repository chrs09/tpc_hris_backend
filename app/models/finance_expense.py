from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FinanceExpense(Base):
    __tablename__ = "tpc_finance_expenses"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # ==============================
    # EXPENSE INFORMATION
    # ==============================

    encoded_date: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    posting_period: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    # ==============================
    # REFERENCE
    # ==============================

    po_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    supplier: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    receipt_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # ==============================
    # RECEIPT / EXPENSE IMAGE
    # ==============================

    receipt_image_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    # ==============================
    # ITEM DETAILS
    # ==============================

    qty: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        default=1,
    )

    unit: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    particulars: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    unit_price: Mapped[float | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    amount: Mapped[float | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    # ==============================
    # ASSIGNMENT
    # ==============================

    responsible: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    additional_details: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    requested_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    received_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ==============================
    # ACCOUNTING
    # ==============================

    category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    account: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ==============================
    # COUNTERING
    # ==============================

    date_countered: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    counter_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # ==============================
    # PAYMENT
    # ==============================

    date_paid: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    bank: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    check_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    check_amount: Mapped[float | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    receipt_number_2: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # ==============================
    # ACCOUNTS PAYABLE
    # ==============================

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Pending",
    )

    ap: Mapped[float | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    remarks: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ==============================
    # AUDIT
    # ==============================

    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )