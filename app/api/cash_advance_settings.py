from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_superadmin
from app.models.user import User
from app.models.cash_advance_deduction_option import CashAdvanceDeductionOption
from app.models.cash_advance_terms import CashAdvanceTerms
from app.schemas.cash_advance_settings import (
    DeductionOptionCreate,
    DeductionOptionUpdate,
    TermsUpdate,
)

router = APIRouter(prefix="/cash-advance-settings", tags=["Cash Advance Settings"])


def _serialize_option(option: CashAdvanceDeductionOption) -> dict:
    return {
        "id": option.id,
        "amount": float(option.amount),
        "label": option.label,
        "is_active": option.is_active,
        "sort_order": option.sort_order,
    }


# =========================
# DEDUCTION OPTIONS
# =========================


@router.get("/deduction-options")
def list_active_deduction_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The picker list shown to a driver filing a cash advance request."""
    options = (
        db.query(CashAdvanceDeductionOption)
        .filter(CashAdvanceDeductionOption.is_active.is_(True))
        .order_by(
            CashAdvanceDeductionOption.sort_order.asc(),
            CashAdvanceDeductionOption.amount.asc(),
        )
        .all()
    )
    return [_serialize_option(o) for o in options]


@router.get("/deduction-options/all")
def list_all_deduction_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Full list (active + inactive) for the superadmin management page."""
    options = (
        db.query(CashAdvanceDeductionOption)
        .order_by(
            CashAdvanceDeductionOption.sort_order.asc(),
            CashAdvanceDeductionOption.amount.asc(),
        )
        .all()
    )
    return [_serialize_option(o) for o in options]


@router.post("/deduction-options")
def create_deduction_option(
    payload: DeductionOptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0.")

    option = CashAdvanceDeductionOption(
        amount=payload.amount,
        label=payload.label,
        sort_order=payload.sort_order,
    )
    db.add(option)
    db.commit()
    db.refresh(option)
    return _serialize_option(option)


@router.patch("/deduction-options/{option_id}")
def update_deduction_option(
    option_id: int,
    payload: DeductionOptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    option = (
        db.query(CashAdvanceDeductionOption)
        .filter(CashAdvanceDeductionOption.id == option_id)
        .first()
    )
    if not option:
        raise HTTPException(status_code=404, detail="Deduction option not found.")

    if payload.amount is not None:
        if payload.amount <= 0:
            raise HTTPException(
                status_code=400, detail="Amount must be greater than 0."
            )
        option.amount = payload.amount
    if payload.label is not None:
        option.label = payload.label
    if payload.is_active is not None:
        option.is_active = payload.is_active
    if payload.sort_order is not None:
        option.sort_order = payload.sort_order

    db.commit()
    db.refresh(option)
    return _serialize_option(option)


@router.delete("/deduction-options/{option_id}")
def delete_deduction_option(
    option_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    option = (
        db.query(CashAdvanceDeductionOption)
        .filter(CashAdvanceDeductionOption.id == option_id)
        .first()
    )
    if not option:
        raise HTTPException(status_code=404, detail="Deduction option not found.")

    # Requests already filed against this option keep their own copy of
    # the amount (CashAdvanceRequest.amount), so deleting the option here
    # never changes historical records.
    db.delete(option)
    db.commit()
    return {"message": "Deduction option deleted."}


# =========================
# TERMS & CONDITIONS
# =========================


@router.get("/terms")
def get_terms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The T&C text a driver must acknowledge before filing. Empty string
    if superadmin hasn't set any yet -- the mobile app should treat that
    as "no acknowledgement required"."""
    terms = db.query(CashAdvanceTerms).order_by(CashAdvanceTerms.id.asc()).first()
    return {
        "content": terms.content if terms else "",
        "max_pay_periods": terms.max_pay_periods if terms else 6,
        "max_loan_amount": (
            float(terms.max_loan_amount)
            if terms and terms.max_loan_amount is not None
            else None
        ),
        "updated_at": terms.updated_at if terms else None,
    }


@router.put("/terms")
def set_terms(
    payload: TermsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    if payload.max_pay_periods <= 0:
        raise HTTPException(
            status_code=400, detail="Max pay periods must be greater than 0."
        )
    if payload.max_loan_amount is not None and payload.max_loan_amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Max loan amount must be greater than 0, or left blank for no cap.",
        )

    terms = db.query(CashAdvanceTerms).order_by(CashAdvanceTerms.id.asc()).first()
    if terms:
        terms.content = payload.content
        terms.max_pay_periods = payload.max_pay_periods
        terms.max_loan_amount = payload.max_loan_amount
        terms.updated_by_user_id = current_user.id
    else:
        terms = CashAdvanceTerms(
            content=payload.content,
            max_pay_periods=payload.max_pay_periods,
            max_loan_amount=payload.max_loan_amount,
            updated_by_user_id=current_user.id,
        )
        db.add(terms)

    db.commit()
    db.refresh(terms)
    return {
        "content": terms.content,
        "max_pay_periods": terms.max_pay_periods,
        "max_loan_amount": (
            float(terms.max_loan_amount)
            if terms.max_loan_amount is not None
            else None
        ),
        "updated_at": terms.updated_at,
    }
