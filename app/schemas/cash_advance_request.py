from pydantic import BaseModel


class CashAdvanceRequestCreate(BaseModel):
    # Total amount requested -- typed freely by the driver.
    amount: float
    # The per-pay deduction amount, picked from a superadmin preset
    # (CashAdvanceDeductionOption).
    deduction_option_id: int
    reason: str
    terms_accepted: bool = False


class CashAdvanceReviewAction(BaseModel):
    remarks: str | None = None


class RecordDeductionCreate(BaseModel):
    # Defaults to the request's deduction_per_pay_amount when omitted.
    amount: float | None = None
    note: str | None = None
