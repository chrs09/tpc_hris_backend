from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role_or_module
from app.models.user import User
from app.models.cash_advance_deduction_option import CashAdvanceDeductionOption
from app.models.cash_advance_terms import CashAdvanceTerms
from app.models.cash_advance_purpose import CashAdvancePurpose
from app.schemas.cash_advance_settings import (
    DeductionOptionCreate,
    DeductionOptionUpdate,
    TermsUpdate,
    PurposeCreate,
    PurposeUpdate,
)

router = APIRouter(prefix="/cash-advance-settings", tags=["Cash Advance Settings"])

_require_cash_advance_settings_access = require_role_or_module(
    roles=[], module_key="administrator.cash_advance_settings"
)


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
    current_user: User = Depends(_require_cash_advance_settings_access),
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
    current_user: User = Depends(_require_cash_advance_settings_access),
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
    current_user: User = Depends(_require_cash_advance_settings_access),
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
    current_user: User = Depends(_require_cash_advance_settings_access),
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
# PURPOSES (preset reasons a driver picks from, instead of free text)
# =========================


def _serialize_purpose(purpose: CashAdvancePurpose) -> dict:
    return {
        "id": purpose.id,
        "label": purpose.label,
        "is_active": purpose.is_active,
        "sort_order": purpose.sort_order,
    }


@router.get("/purposes")
def list_active_purposes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The picker list shown to a driver filing a cash advance request."""
    purposes = (
        db.query(CashAdvancePurpose)
        .filter(CashAdvancePurpose.is_active.is_(True))
        .order_by(
            CashAdvancePurpose.sort_order.asc(),
            CashAdvancePurpose.label.asc(),
        )
        .all()
    )
    return [_serialize_purpose(p) for p in purposes]


@router.get("/purposes/all")
def list_all_purposes(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_cash_advance_settings_access),
):
    """Full list (active + inactive) for the superadmin management page."""
    purposes = (
        db.query(CashAdvancePurpose)
        .order_by(
            CashAdvancePurpose.sort_order.asc(),
            CashAdvancePurpose.label.asc(),
        )
        .all()
    )
    return [_serialize_purpose(p) for p in purposes]


@router.post("/purposes")
def create_purpose(
    payload: PurposeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_cash_advance_settings_access),
):
    if not payload.label.strip():
        raise HTTPException(status_code=400, detail="Label is required.")

    purpose = CashAdvancePurpose(
        label=payload.label.strip(),
        sort_order=payload.sort_order,
    )
    db.add(purpose)
    db.commit()
    db.refresh(purpose)
    return _serialize_purpose(purpose)


@router.patch("/purposes/{purpose_id}")
def update_purpose(
    purpose_id: int,
    payload: PurposeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_cash_advance_settings_access),
):
    purpose = (
        db.query(CashAdvancePurpose)
        .filter(CashAdvancePurpose.id == purpose_id)
        .first()
    )
    if not purpose:
        raise HTTPException(status_code=404, detail="Purpose not found.")

    if payload.label is not None:
        if not payload.label.strip():
            raise HTTPException(status_code=400, detail="Label is required.")
        purpose.label = payload.label.strip()
    if payload.is_active is not None:
        purpose.is_active = payload.is_active
    if payload.sort_order is not None:
        purpose.sort_order = payload.sort_order

    db.commit()
    db.refresh(purpose)
    return _serialize_purpose(purpose)


@router.delete("/purposes/{purpose_id}")
def delete_purpose(
    purpose_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_cash_advance_settings_access),
):
    purpose = (
        db.query(CashAdvancePurpose)
        .filter(CashAdvancePurpose.id == purpose_id)
        .first()
    )
    if not purpose:
        raise HTTPException(status_code=404, detail="Purpose not found.")

    # Requests already filed keep their own copy of the label text
    # (CashAdvanceRequest.reason), so deleting the purpose here never
    # changes historical records.
    db.delete(purpose)
    db.commit()
    return {"message": "Purpose deleted."}


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
        "max_active_requests": terms.max_active_requests if terms else None,
        "updated_at": terms.updated_at if terms else None,
    }


@router.put("/terms")
def set_terms(
    payload: TermsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_cash_advance_settings_access),
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
    if payload.max_active_requests is not None and payload.max_active_requests <= 0:
        raise HTTPException(
            status_code=400,
            detail="Max active requests must be greater than 0, or left blank for no cap.",
        )

    terms = db.query(CashAdvanceTerms).order_by(CashAdvanceTerms.id.asc()).first()
    if terms:
        terms.content = payload.content
        terms.max_pay_periods = payload.max_pay_periods
        terms.max_loan_amount = payload.max_loan_amount
        terms.max_active_requests = payload.max_active_requests
        terms.updated_by_user_id = current_user.id
    else:
        terms = CashAdvanceTerms(
            content=payload.content,
            max_pay_periods=payload.max_pay_periods,
            max_loan_amount=payload.max_loan_amount,
            max_active_requests=payload.max_active_requests,
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
        "max_active_requests": terms.max_active_requests,
        "updated_at": terms.updated_at,
    }
