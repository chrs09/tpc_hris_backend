# app/api/loan_amortization.py
#
# Finance -> Loan Amortization: SSS and Pag-IBIG loans that payroll pays
# down. Admin or anyone granted finance.loan_amortization enters the
# amount borrowed, the monthly amortization and the terms; the pay run
# (Deductions step) then takes the amortization each cutoff
# (app/services/loan_payroll.py).

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.employee_loan import (
    LOAN_TYPES,
    SCHEDULES,
    EmployeeLoan,
    EmployeeLoanPayment,
)
from app.models.employees import Employee
from app.models.user import User
from app.services.loan_payroll import _money, paid_by_loan, total_payable

router = APIRouter(prefix="/loan-amortization", tags=["Loan Amortization"])

MODULE = "finance.loan_amortization"
_require_view = require_role_or_module(roles=["admin"], module_key=MODULE)


def _ensure_can_edit(db: Session, user: User):
    from app.core.dependencies import has_editable_grant

    role = user.role.value if hasattr(user.role, "value") else user.role
    if role in ("superadmin", "admin") or has_editable_grant(db, user, [MODULE]):
        return
    raise HTTPException(status_code=403, detail="You can view this page but not edit it.")


def _name(emp: Employee | None) -> str:
    if emp is None:
        return "Unknown employee"
    return f"{emp.last_name}, {emp.first_name}" + (f" {emp.suffix}" if emp.suffix else "")


def _row(loan: EmployeeLoan, emp: Employee | None, paid: float, payments: int, last_paid=None) -> dict:
    payable = float(total_payable(loan))
    opening = float(loan.opening_paid or 0)
    total_paid = round(opening + paid, 2)
    balance = round(max(payable - total_paid, 0), 2)
    monthly = float(loan.monthly_amortization or 0)
    months_paid = round(total_paid / monthly, 1) if monthly else 0
    status = loan.status
    if status == "ACTIVE" and balance <= 0:
        status = "PAID"
    return {
        "id": loan.id,
        "employee_id": loan.employee_id,
        "employee_name": _name(emp),
        "department": emp.department if emp else None,
        "loan_type": loan.loan_type,
        "reference_no": loan.reference_no,
        "loan_amount": float(loan.loan_amount or 0),
        "monthly_amortization": monthly,
        "terms_months": loan.terms_months,
        "start_date": loan.start_date.isoformat() if loan.start_date else None,
        "deduct_schedule": loan.deduct_schedule,
        "opening_paid": opening,
        "notes": loan.notes,
        "total_payable": round(payable, 2),
        "total_paid": total_paid,
        "balance": balance,
        "months_paid": months_paid,
        "months_left": max(round(loan.terms_months - months_paid, 1), 0),
        "payments": payments,
        "last_paid_cutoff": last_paid,
        "status": status,  # ACTIVE | PAID | CANCELLED
    }


def _rows(db: Session, loans: list[EmployeeLoan]) -> list[dict]:
    ids = [l.id for l in loans]
    other, _ = paid_by_loan(db, ids)
    counts: dict[int, int] = {}
    last: dict[int, str] = {}
    for p in db.query(EmployeeLoanPayment).filter(EmployeeLoanPayment.loan_id.in_(ids or [0])):
        counts[p.loan_id] = counts.get(p.loan_id, 0) + 1
        if p.cutoff_period and p.cutoff_period > last.get(p.loan_id, ""):
            last[p.loan_id] = p.cutoff_period
    emp_ids = {l.employee_id for l in loans}
    emps = {e.id: e for e in db.query(Employee).filter(Employee.id.in_(emp_ids or [0]))}
    return [
        _row(l, emps.get(l.employee_id), float(other[l.id]), counts.get(l.id, 0), last.get(l.id))
        for l in loans
    ]


@router.get("")
def list_loans(
    loan_type: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    q = db.query(EmployeeLoan)
    if loan_type:
        q = q.filter(EmployeeLoan.loan_type == loan_type)
    return _rows(db, q.order_by(EmployeeLoan.created_at.desc(), EmployeeLoan.id.desc()).all())


@router.get("/employees")
def loan_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    """Active employees for the Add loan picker."""
    emps = (
        db.query(Employee)
        .filter(Employee.is_active == 1)
        .order_by(Employee.last_name, Employee.first_name)
        .all()
    )
    return [{"id": e.id, "name": _name(e), "department": e.department} for e in emps]


class LoanIn(BaseModel):
    employee_id: int
    loan_type: str
    reference_no: str | None = None
    loan_amount: float = Field(gt=0)
    monthly_amortization: float = Field(gt=0)
    terms_months: int = Field(gt=0, le=600)
    start_date: date
    deduct_schedule: str = "SPLIT"
    opening_paid: float = Field(0, ge=0)
    notes: str | None = None


def _validate(payload: LoanIn):
    if payload.loan_type not in LOAN_TYPES:
        raise HTTPException(status_code=400, detail="Loan type must be SSS or Pag-IBIG.")
    if payload.deduct_schedule not in SCHEDULES:
        raise HTTPException(status_code=400, detail="Unknown deduction schedule.")
    if payload.opening_paid > payload.monthly_amortization * payload.terms_months:
        raise HTTPException(status_code=400, detail="Already paid is more than the loan's total.")


def _apply(loan: EmployeeLoan, payload: LoanIn):
    loan.employee_id = payload.employee_id
    loan.loan_type = payload.loan_type
    loan.reference_no = (payload.reference_no or "").strip()[:60] or None
    loan.loan_amount = round(payload.loan_amount, 2)
    loan.monthly_amortization = round(payload.monthly_amortization, 2)
    loan.terms_months = payload.terms_months
    loan.start_date = payload.start_date.replace(day=1)
    loan.deduct_schedule = payload.deduct_schedule
    loan.opening_paid = round(payload.opening_paid or 0, 2)
    loan.notes = (payload.notes or "").strip()[:300] or None


def _one(db: Session, loan: EmployeeLoan) -> dict:
    return _rows(db, [loan])[0]


@router.post("")
def create_loan(
    payload: LoanIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    _ensure_can_edit(db, current_user)
    _validate(payload)
    if db.get(Employee, payload.employee_id) is None:
        raise HTTPException(status_code=404, detail="Employee not found.")
    loan = EmployeeLoan(created_by=current_user.id, status="ACTIVE")
    _apply(loan, payload)
    db.add(loan)
    db.commit()
    db.refresh(loan)
    return _one(db, loan)


def _get(db: Session, loan_id: int) -> EmployeeLoan:
    loan = db.get(EmployeeLoan, loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found.")
    return loan


@router.put("/{loan_id}")
def update_loan(
    loan_id: int,
    payload: LoanIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    _ensure_can_edit(db, current_user)
    _validate(payload)
    loan = _get(db, loan_id)
    has_payments = db.query(EmployeeLoanPayment.id).filter(EmployeeLoanPayment.loan_id == loan.id).first()
    if has_payments and (payload.employee_id != loan.employee_id or payload.loan_type != loan.loan_type):
        raise HTTPException(
            status_code=400,
            detail="Payroll already deducted this loan; the employee and loan type can't change.",
        )
    _apply(loan, payload)
    db.commit()
    db.refresh(loan)
    return _one(db, loan)


class StatusIn(BaseModel):
    status: str  # ACTIVE | CANCELLED


@router.post("/{loan_id}/status")
def set_status(
    loan_id: int,
    payload: StatusIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    """Cancel (stop deducting, e.g. paid off outside payroll) or reopen."""
    _ensure_can_edit(db, current_user)
    if payload.status not in ("ACTIVE", "CANCELLED"):
        raise HTTPException(status_code=400, detail="Unknown status.")
    loan = _get(db, loan_id)
    loan.status = payload.status
    db.commit()
    return _one(db, loan)


@router.delete("/{loan_id}")
def delete_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    """Only a loan payroll never deducted (entered by mistake)."""
    _ensure_can_edit(db, current_user)
    loan = _get(db, loan_id)
    if db.query(EmployeeLoanPayment.id).filter(EmployeeLoanPayment.loan_id == loan.id).first():
        raise HTTPException(status_code=400, detail="Payroll already deducted this loan. Cancel it instead.")
    db.delete(loan)
    db.commit()
    return {"deleted": loan_id}


@router.get("/{loan_id}/payments")
def loan_payments(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    loan = _get(db, loan_id)
    payments = (
        db.query(EmployeeLoanPayment)
        .filter(EmployeeLoanPayment.loan_id == loan.id)
        .order_by(EmployeeLoanPayment.created_at.asc(), EmployeeLoanPayment.id.asc())
        .all()
    )
    users = {
        u.id: u.username
        for u in db.query(User).filter(User.id.in_({p.recorded_by for p in payments if p.recorded_by} or {0}))
    }
    return {
        "loan": _one(db, loan),
        "payments": [
            {
                "id": p.id,
                "amount": float(p.amount),
                "cutoff_period": p.cutoff_period,
                "note": p.note,
                "recorded_by": users.get(p.recorded_by),
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in payments
        ],
    }


class PaymentIn(BaseModel):
    amount: float = Field(gt=0)
    note: str | None = None


@router.post("/{loan_id}/payments")
def add_payment(
    loan_id: int,
    payload: PaymentIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_view),
):
    """A payment made outside payroll (e.g. paid at the SSS branch)."""
    _ensure_can_edit(db, current_user)
    loan = _get(db, loan_id)
    row = _one(db, loan)
    if payload.amount > row["balance"] + 0.005:
        raise HTTPException(status_code=400, detail=f"Only ₱{row['balance']:,.2f} is left on this loan.")
    db.add(EmployeeLoanPayment(
        loan_id=loan.id, amount=_money(payload.amount), cutoff_period=None,
        note=(payload.note or "").strip()[:200] or "Paid outside payroll", recorded_by=current_user.id,
    ))
    db.commit()
    return _one(db, loan)

