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


class OpeningBalanceCreate(BaseModel):
    # A pre-existing balance carried over from before this system was
    # used (e.g. a manual/paper ledger) -- created directly as an
    # already-approved request by a superadmin, not filed by the
    # employee.
    user_id: int
    amount: float
    # How much to deduct per pay period going forward. Defaults to the
    # full amount (a single lump-sum "period") if left blank.
    deduction_per_pay_amount: float | None = None
    note: str | None = None
