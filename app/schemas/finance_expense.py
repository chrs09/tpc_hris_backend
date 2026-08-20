from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FinanceExpenseBase(BaseModel):
    # ==============================
    # EXPENSE INFORMATION
    # ==============================

    posting_period: Optional[str] = None
    date: Optional[date] = None

    # ==============================
    # REFERENCE
    # ==============================

    po_number: Optional[str] = None
    supplier: Optional[str] = None
    receipt_number: Optional[str] = None

    # ==============================
    # ITEM DETAILS
    # ==============================

    qty: Optional[float] = Field(
        default=1,
        ge=0,
    )

    unit: Optional[str] = None

    particulars: Optional[str] = None

    unit_price: Optional[float] = Field(
        default=None,
        ge=0,
    )

    amount: Optional[float] = Field(
        default=None,
        ge=0,
    )

    # ==============================
    # ASSIGNMENT
    # ==============================

    responsible: Optional[str] = None

    additional_details: Optional[str] = None

    requested_by: Optional[str] = None

    received_by: Optional[str] = None

    # ==============================
    # ACCOUNTING
    # ==============================

    category: Optional[str] = None

    account: Optional[str] = None

    notes: Optional[str] = None

    # ==============================
    # COUNTERING
    # ==============================

    date_countered: Optional[date] = None

    counter_number: Optional[str] = None

    # ==============================
    # PAYMENT
    # ==============================

    date_paid: Optional[date] = None

    bank: Optional[str] = None

    check_number: Optional[str] = None

    check_amount: Optional[float] = Field(
        default=None,
        ge=0,
    )

    receipt_number_2: Optional[str] = None

    # ==============================
    # ACCOUNTS PAYABLE
    # ==============================

    status: Optional[str] = "Pending"

    ap: Optional[float] = Field(
        default=None,
        ge=0,
    )

    remarks: Optional[str] = None


class FinanceExpenseCreate(FinanceExpenseBase):
    pass


class FinanceExpenseUpdate(BaseModel):
    posting_period: Optional[str] = None
    date: Optional[date] = None

    po_number: Optional[str] = None
    supplier: Optional[str] = None
    receipt_number: Optional[str] = None

    qty: Optional[float] = Field(
        default=None,
        ge=0,
    )

    unit: Optional[str] = None
    particulars: Optional[str] = None

    unit_price: Optional[float] = Field(
        default=None,
        ge=0,
    )

    amount: Optional[float] = Field(
        default=None,
        ge=0,
    )

    responsible: Optional[str] = None
    additional_details: Optional[str] = None
    requested_by: Optional[str] = None
    received_by: Optional[str] = None

    category: Optional[str] = None
    account: Optional[str] = None
    notes: Optional[str] = None

    date_countered: Optional[date] = None
    counter_number: Optional[str] = None

    date_paid: Optional[date] = None
    bank: Optional[str] = None
    check_number: Optional[str] = None

    check_amount: Optional[float] = Field(
        default=None,
        ge=0,
    )

    receipt_number_2: Optional[str] = None

    status: Optional[str] = None

    ap: Optional[float] = Field(
        default=None,
        ge=0,
    )

    remarks: Optional[str] = None


class FinanceExpenseResponse(FinanceExpenseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int

    encoded_date: Optional[datetime] = None

    receipt_image_url: Optional[str] = None

    created_by_user_id: Optional[int] = None
    updated_by_user_id: Optional[int] = None

    created_at: datetime
    updated_at: datetime