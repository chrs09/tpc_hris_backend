from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FinanceExpenseItem(Base):
    __tablename__ = "tpc_finance_expense_items"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    expense_id: Mapped[int] = mapped_column(
        ForeignKey("tpc_finance_expenses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    particulars: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    qty: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=1,
    )

    unit: Mapped[str | None] = mapped_column(
        String(50),
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
    expense: Mapped["FinanceExpense"] = relationship(
        "FinanceExpense",
        back_populates="items",
    )