from pydantic import BaseModel


class DeductionOptionCreate(BaseModel):
    amount: float
    label: str | None = None
    sort_order: int = 0


class DeductionOptionUpdate(BaseModel):
    amount: float | None = None
    label: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class TermsUpdate(BaseModel):
    content: str
    max_pay_periods: int = 6
    # Largest total amount a single request may ask for. None = no cap.
    max_loan_amount: float | None = None
