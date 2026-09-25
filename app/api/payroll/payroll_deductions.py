from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.models.user import User
from app.models.employees import Employee
from app.models.payroll_deductions import PayrollDeduction
from app.services.cash_advance_payroll import (
    apply_payroll_deduction,
    payroll_suggestions,
)

router = APIRouter(
    prefix="/payroll-deductions",
    tags=["Payroll Deductions"],
)


def _save_deduction(
    db: Session, payload: dict, user_id: int | None = None
) -> PayrollDeduction:
    employee = (
        db.query(Employee).filter(Employee.id == payload["employee_id"]).first()
    )

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found.",
        )

    existing = (
        db.query(PayrollDeduction)
        .filter(
            PayrollDeduction.employee_id == payload["employee_id"],
            PayrollDeduction.cutoff_period == payload["cutoff_period"],
        )
        .first()
    )

    # Post this cutoff's cash advance deduction to the employee's cash
    # advance balance (replacing any earlier post for the same cutoff),
    # capped at what they actually owe. Only when the client sends the
    # field, so older clients don't wipe an existing deduction.
    if "cash_advance_deduction" in payload:
        ca = apply_payroll_deduction(
            db,
            payload["employee_id"],
            payload["cutoff_period"],
            payload.get("cash_advance_deduction") or 0,
            user_id,
        )
        payload["cash_advance_deduction"] = ca["applied"]

    if existing:
        existing.department = payload["department"]

        existing.gross_pay = payload["gross_pay"]

        existing.sss_deduction = payload["sss_deduction"]

        existing.philhealth_deduction = payload["philhealth_deduction"]

        existing.pagibig_deduction = payload["pagibig_deduction"]

        existing.tardiness_deduction = payload.get("tardiness_deduction", 0)

        existing.undertime_deduction = payload.get("undertime_deduction", 0)

        existing.absent_deduction = payload.get("absent_deduction", 0)

        if "cash_advance_deduction" in payload:
            existing.cash_advance_deduction = payload["cash_advance_deduction"]

        existing.net_pay = payload["net_pay"]

        existing.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(existing)

        return existing

    deduction = PayrollDeduction(
        cutoff_period=payload["cutoff_period"],
        employee_id=payload["employee_id"],
        department=payload["department"],
        gross_pay=payload["gross_pay"],
        sss_deduction=payload["sss_deduction"],
        philhealth_deduction=payload["philhealth_deduction"],
        pagibig_deduction=payload["pagibig_deduction"],
        tardiness_deduction=payload.get("tardiness_deduction", 0),
        undertime_deduction=payload.get("undertime_deduction", 0),
        absent_deduction=payload.get("absent_deduction", 0),
        cash_advance_deduction=payload.get("cash_advance_deduction", 0),
        net_pay=payload["net_pay"],
    )

    db.add(deduction)

    db.commit()
    db.refresh(deduction)

    return deduction


@router.post("/save")
def save_payroll_deduction(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [
        "admin",
        "superadmin",
    ]:
        raise HTTPException(
            status_code=403,
            detail="Only HR/Admin can save payroll deductions.",
        )

    deduction = _save_deduction(db, payload, current_user.id)

    return {
        "message": "Deduction saved.",
        "id": deduction.id,
    }


@router.post("/save-bulk")
def save_payroll_deductions_bulk(
    payload: list[dict],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [
        "admin",
        "superadmin",
    ]:
        raise HTTPException(
            status_code=403,
            detail="Only HR/Admin can save payroll deductions.",
        )

    ids = [_save_deduction(db, item, current_user.id).id for item in payload]

    return {
        "message": f"{len(ids)} deduction(s) saved.",
        "ids": ids,
    }


@router.get("/cash-advance")
def get_cash_advance_for_cutoff(
    cutoff_period: str,
    employee_ids: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cash advance to deduct this cutoff, per employee (comma-separated
    ids): the suggested amount from their approved advances, what was
    already posted for this cutoff (if the payslip was generated before),
    and the balance owed before this cutoff."""
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Not allowed.")
    try:
        ids = [int(x) for x in employee_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid employee ids.")
    suggestions = payroll_suggestions(db, ids, cutoff_period)
    return {str(emp): data for emp, data in suggestions.items()}


@router.get("/list")
def get_payroll_deductions(
    cutoff_period: str | None = None,
    department: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(PayrollDeduction)

    if cutoff_period:
        query = query.filter(PayrollDeduction.cutoff_period == cutoff_period)

    if department:
        query = query.filter(PayrollDeduction.department == department)

    records = query.order_by(PayrollDeduction.cutoff_period.desc()).all()

    return records


@router.get("/employee/{employee_id}")
def get_employee_payroll_deductions(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    records = (
        db.query(PayrollDeduction)
        .filter(PayrollDeduction.employee_id == employee_id)
        .order_by(PayrollDeduction.cutoff_period.desc())
        .all()
    )

    return records