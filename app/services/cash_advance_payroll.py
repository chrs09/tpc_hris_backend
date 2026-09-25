"""Connects cash advance balances to payroll.

Each approved cash advance (including opening balances) is paid down by
its per-pay amount every payroll cutoff. The amount is suggested to
payroll (see `payroll_suggestions`) and becomes real when the payslip is
generated (see `apply_payroll_deduction`), as CashAdvanceDeductionLog
entries tagged with that cutoff -- so a request's balance is still just
approved amount minus its logs, and regenerating the same cutoff
replaces that cutoff's entries instead of deducting twice.
"""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.cash_advance_deduction_log import CashAdvanceDeductionLog
from app.models.cash_advance_request import CashAdvanceRequest
from app.models.user import User

CENT = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _approved_requests(db: Session, employee_ids: list[int]) -> dict[int, list]:
    """Approved requests per employee, oldest first (paid down first).
    Matches on the request's employee, or -- for a request filed before
    employee_id was recorded -- on the filer's linked employee."""
    if not employee_ids:
        return {}
    user_employee = {
        uid: eid
        for uid, eid in db.query(User.id, User.employee_id)
        .filter(User.employee_id.in_(employee_ids))
        .all()
    }
    rows = (
        db.query(CashAdvanceRequest)
        .filter(
            CashAdvanceRequest.status == "approved",
            or_(
                CashAdvanceRequest.employee_id.in_(employee_ids),
                CashAdvanceRequest.user_id.in_(list(user_employee) or [0]),
            ),
        )
        .order_by(CashAdvanceRequest.approved_at.asc(), CashAdvanceRequest.id.asc())
        .all()
    )
    by_employee = defaultdict(list)
    for req in rows:
        emp = req.employee_id or user_employee.get(req.user_id)
        if emp in employee_ids:
            by_employee[emp].append(req)
    return by_employee


def _deducted(db: Session, request_ids: list[int], cutoff_period: str):
    """(deducted outside this cutoff, deducted in this cutoff) per request."""
    other = defaultdict(Decimal)
    this = defaultdict(Decimal)
    if not request_ids:
        return other, this
    for log in db.query(CashAdvanceDeductionLog).filter(
        CashAdvanceDeductionLog.cash_advance_request_id.in_(request_ids)
    ):
        bucket = this if log.payroll_cutoff_period == cutoff_period else other
        bucket[log.cash_advance_request_id] += _money(log.amount)
    return other, this


def _payable(req: CashAdvanceRequest) -> Decimal:
    return _money(
        req.approved_amount if req.approved_amount is not None else req.amount
    )


def payroll_suggestions(
    db: Session, employee_ids: list[int], cutoff_period: str
) -> dict[int, dict]:
    """Per employee with an outstanding (or this-cutoff) cash advance:
    - suggested: sum of each advance's per-pay amount, capped at what's left
    - posted: what was already deducted for this cutoff (if generated before)
    - balance_before: total owed before this cutoff's deduction
    """
    by_employee = _approved_requests(db, employee_ids)
    request_ids = [r.id for reqs in by_employee.values() for r in reqs]
    other, this = _deducted(db, request_ids, cutoff_period)

    result = {}
    for emp, reqs in by_employee.items():
        balance_before = Decimal("0")
        suggested = Decimal("0")
        posted = Decimal("0")
        for req in reqs:
            remaining = max(_payable(req) - other[req.id], Decimal("0"))
            balance_before += remaining
            suggested += min(_money(req.deduction_per_pay_amount), remaining)
            posted += this[req.id]
        if balance_before <= 0 and posted <= 0:
            continue
        result[emp] = {
            "suggested": float(suggested),
            "posted": float(posted) if posted > 0 else None,
            "balance_before": float(balance_before),
        }
    return result


def apply_payroll_deduction(
    db: Session,
    employee_id: int,
    cutoff_period: str,
    amount,
    user_id: int | None,
) -> dict:
    """Records `amount` as this cutoff's cash advance deduction for the
    employee, replacing anything recorded for the same cutoff before.
    Spread across their advances oldest first, never beyond what's owed.
    Does not commit. Returns the amount actually applied and the balance
    left afterwards."""
    by_employee = _approved_requests(db, [employee_id])
    reqs = by_employee.get(employee_id, [])
    request_ids = [r.id for r in reqs]

    if request_ids:
        db.query(CashAdvanceDeductionLog).filter(
            CashAdvanceDeductionLog.cash_advance_request_id.in_(request_ids),
            CashAdvanceDeductionLog.payroll_cutoff_period == cutoff_period,
        ).delete(synchronize_session=False)

    other, _ = _deducted(db, request_ids, cutoff_period)
    to_apply = max(_money(amount), Decimal("0"))
    remaining = {
        req.id: max(_payable(req) - other[req.id], Decimal("0")) for req in reqs
    }
    take = defaultdict(Decimal)
    left = to_apply

    # First each advance's own per-pay amount (its agreed schedule), then
    # anything extra HR entered goes to the oldest advance first.
    for req in reqs:
        share = min(_money(req.deduction_per_pay_amount), remaining[req.id], left)
        take[req.id] += share
        left -= share
    for req in reqs:
        extra = min(remaining[req.id] - take[req.id], left)
        take[req.id] += extra
        left -= extra

    for req in reqs:
        if take[req.id] > 0:
            db.add(
                CashAdvanceDeductionLog(
                    cash_advance_request_id=req.id,
                    amount=take[req.id],
                    note=f"Payroll deduction ({cutoff_period.replace('_', ' to ')})",
                    recorded_by_user_id=user_id,
                    payroll_cutoff_period=cutoff_period,
                )
            )

    applied = sum(take.values(), Decimal("0"))
    balance_after = sum(remaining.values(), Decimal("0")) - applied
    return {"applied": float(applied), "balance_after": float(balance_after)}
