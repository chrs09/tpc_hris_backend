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
    # Approval only -- lets the approver grant less than what was
    # requested (e.g. requested 5000, approve 3000). Ignored on reject.
    # Defaults to the full requested amount when omitted.
    approved_amount: float | None = None


class ReleaseInfoUpdate(BaseModel):
    # Proof the approved funds were actually handed over -- a GCash
    # reference number, check number, payroll-release note, etc.
    release_reference: str


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
