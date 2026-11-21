"""Connects SSS / Pag-IBIG loans (Finance -> Loan Amortization) to payroll.

What a cutoff deducts: the monthly amortization is due on two days of the
month -- the 15th and the last day. A cutoff takes the part of each due
day it covers:
- SPLIT  : half on the 15th, half on the last day
- FIRST  : all of it on the 15th
- SECOND : all of it on the last day
So a 1-15 / 16-end pay group takes half each cutoff, a monthly run takes
all of it, and a weekly run takes it in the week holding the due day.

Nothing is owed before the loan's start month, and never more than what's
left (monthly amortization x terms, less what was paid). The deduction
becomes real at Generate / the Deductions step (apply_loan_deduction), as
EmployeeLoanPayment rows tagged with the cutoff.
"""

import calendar
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models.employee_loan import EmployeeLoan, EmployeeLoanPayment

CENT = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def total_payable(loan: EmployeeLoan) -> Decimal:
    return _money(loan.monthly_amortization) * int(loan.terms_months or 0)


def parse_cutoff(cutoff_period: str) -> tuple[date, date] | None:
    try:
        start, end = cutoff_period.split("_")
        return date.fromisoformat(start), date.fromisoformat(end)
    except (ValueError, AttributeError):
        return None


def _due_days(start: date, end: date):
    """(due date, which) for every 15th / month end inside the cutoff."""
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        last = calendar.monthrange(y, m)[1]
        for day, which in ((15, "FIRST"), (last, "SECOND")):
            d = date(y, m, day)
            if start <= d <= end:
                out.append((d, which))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def amount_due(loan: EmployeeLoan, cutoff_period: str) -> Decimal:
    """This cutoff's scheduled amortization (before capping at the balance)."""
    span = parse_cutoff(cutoff_period)
    if not span:
        return Decimal("0")
    first_month = loan.start_date.replace(day=1)
    monthly = _money(loan.monthly_amortization)
    due = Decimal("0")
    for d, which in _due_days(*span):
        if d < first_month:
            continue
        if loan.deduct_schedule == "SPLIT":
            due += monthly / 2
        elif loan.deduct_schedule == which:
            due += monthly
    return _money(due)


def _loans(db: Session, employee_ids: list[int], loan_type: str | None = None):
    if not employee_ids:
        return []
    q = db.query(EmployeeLoan).filter(EmployeeLoan.employee_id.in_(employee_ids))
    if loan_type:
        q = q.filter(EmployeeLoan.loan_type == loan_type)
    return q.order_by(EmployeeLoan.start_date.asc(), EmployeeLoan.id.asc()).all()


def paid_by_loan(db: Session, loan_ids: list[int], cutoff_period: str | None = None):
    """(paid outside this cutoff, paid in this cutoff) per loan."""
    other = defaultdict(Decimal)
    this = defaultdict(Decimal)
    if not loan_ids:
        return other, this
    for p in db.query(EmployeeLoanPayment).filter(EmployeeLoanPayment.loan_id.in_(loan_ids)):
        bucket = this if cutoff_period and p.cutoff_period == cutoff_period else other
        bucket[p.loan_id] += _money(p.amount)
    return other, this


def _remaining(loan: EmployeeLoan, paid_other: Decimal) -> Decimal:
    return max(total_payable(loan) - _money(loan.opening_paid) - paid_other, Decimal("0"))


def payroll_suggestions(db: Session, employee_ids: list[int], cutoff_period: str) -> dict:
    """{employee_id: {"SSS": {...}, "PAGIBIG": {...}}} for everyone with a
    loan owing (or already paid this cutoff):
    - suggested: this cutoff's amortization, capped at what's left
    - posted: what was already deducted for this cutoff
    - balance_before: what's left before this cutoff
    """
    loans = _loans(db, employee_ids)
    other, this = paid_by_loan(db, [l.id for l in loans], cutoff_period)
    result: dict = {}
    for loan in loans:
        remaining = _remaining(loan, other[loan.id])
        active = loan.status == "ACTIVE"
        if (not active or remaining <= 0) and this[loan.id] <= 0:
            continue
        slot = result.setdefault(loan.employee_id, {}).setdefault(
            loan.loan_type, {"suggested": Decimal("0"), "posted": Decimal("0"), "balance_before": Decimal("0")}
        )
        if active:
            slot["balance_before"] += remaining
            slot["suggested"] += min(amount_due(loan, cutoff_period), remaining)
        slot["posted"] += this[loan.id]
    for emp in result.values():
        for slot in emp.values():
            posted = slot["posted"]
            slot["suggested"] = float(slot["suggested"])
            slot["balance_before"] = float(slot["balance_before"])
            slot["posted"] = float(posted) if posted > 0 else None
    return result


def has_loans(db: Session, employee_id: int, loan_type: str) -> bool:
    return (
        db.query(EmployeeLoan.id)
        .filter(EmployeeLoan.employee_id == employee_id, EmployeeLoan.loan_type == loan_type)
        .first()
        is not None
    )


def apply_loan_deduction(
    db: Session, employee_id: int, loan_type: str, cutoff_period: str, amount, user_id: int | None
) -> dict | None:
    """Records `amount` as this cutoff's loan deduction, replacing any
    earlier one for the same cutoff, oldest loan first and never beyond
    what's owed. Returns None when the employee has no loan of this type
    (the amount is then just kept on the payslip, untracked). Doesn't commit."""
    loans = _loans(db, [employee_id], loan_type)
    if not loans:
        return None
    ids = [l.id for l in loans]
    db.query(EmployeeLoanPayment).filter(
        EmployeeLoanPayment.loan_id.in_(ids),
        EmployeeLoanPayment.cutoff_period == cutoff_period,
    ).delete(synchronize_session=False)

    other, _ = paid_by_loan(db, ids, cutoff_period)
    active = [l for l in loans if l.status == "ACTIVE"]
    remaining = {l.id: _remaining(l, other[l.id]) for l in active}
    take = defaultdict(Decimal)
    left = max(_money(amount), Decimal("0"))
    # Each loan's own amortization first, then any extra to the oldest.
    for loan in active:
        share = min(amount_due(loan, cutoff_period), remaining[loan.id], left)
        take[loan.id] += share
        left -= share
    for loan in active:
        extra = min(remaining[loan.id] - take[loan.id], left)
        take[loan.id] += extra
        left -= extra

    label = cutoff_period.replace("_", " to ")
    for loan in active:
        if take[loan.id] > 0:
            db.add(EmployeeLoanPayment(
                loan_id=loan.id, amount=take[loan.id], cutoff_period=cutoff_period,
                note=f"Payroll deduction ({label})", recorded_by=user_id,
            ))
    applied = sum(take.values(), Decimal("0"))
    return {
        "applied": float(applied),
        "balance_after": float(sum(remaining.values(), Decimal("0")) - applied),
    }
