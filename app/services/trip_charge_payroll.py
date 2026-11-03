"""Connects approved trip charges to payroll, the same way
cash_advance_payroll.py does for cash advances: each cutoff suggests each
person's per-pay amount, and generating the payslip makes it real as log
entries tagged with that cutoff, so regenerating replaces them instead of
deducting twice. A late charge lands on the next open cutoff, because
locked cutoffs can't be saved at all (ensure_payroll_editable).
"""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models.trip_charge import (
    TripCharge,
    TripChargeAllocation,
    TripChargeDeductionLog,
)

CENT = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _approved_allocations(db: Session, employee_ids: list[int]) -> dict[int, list]:
    """Approved allocations per employee, oldest first (paid down first)."""
    if not employee_ids:
        return {}
    rows = (
        db.query(TripChargeAllocation)
        .join(TripCharge, TripCharge.id == TripChargeAllocation.trip_charge_id)
        .filter(
            TripCharge.status == "approved",
            TripChargeAllocation.employee_id.in_(employee_ids),
        )
        .order_by(TripCharge.approved_at.asc(), TripChargeAllocation.id.asc())
        .all()
    )
    by_employee = defaultdict(list)
    for allocation in rows:
        by_employee[allocation.employee_id].append(allocation)
    return by_employee


def _deducted(db: Session, allocation_ids: list[int], cutoff_period: str):
    """(deducted outside this cutoff, deducted in this cutoff) per allocation."""
    other = defaultdict(Decimal)
    this = defaultdict(Decimal)
    if not allocation_ids:
        return other, this
    for log in db.query(TripChargeDeductionLog).filter(
        TripChargeDeductionLog.allocation_id.in_(allocation_ids)
    ):
        bucket = this if log.payroll_cutoff_period == cutoff_period else other
        bucket[log.allocation_id] += _money(log.amount)
    return other, this


def _per_pay(allocation, remaining: Decimal) -> Decimal:
    if allocation.deduction_per_pay is None:
        return remaining
    return min(_money(allocation.deduction_per_pay), remaining)


def payroll_suggestions(
    db: Session, employee_ids: list[int], cutoff_period: str
) -> dict[int, dict]:
    """Per employee with an outstanding (or this-cutoff) charge: suggested
    per-pay total, what's already posted this cutoff, and the balance before
    this cutoff. Same shape as the cash advance suggestions."""
    by_employee = _approved_allocations(db, employee_ids)
    allocation_ids = [a.id for rows in by_employee.values() for a in rows]
    other, this = _deducted(db, allocation_ids, cutoff_period)

    result = {}
    for emp, rows in by_employee.items():
        balance_before = Decimal("0")
        suggested = Decimal("0")
        posted = Decimal("0")
        for allocation in rows:
            remaining = max(_money(allocation.amount) - other[allocation.id], Decimal("0"))
            balance_before += remaining
            suggested += _per_pay(allocation, remaining)
            posted += this[allocation.id]
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
    """Records `amount` as this cutoff's trip charge deduction, replacing
    anything recorded for the same cutoff before. Spread oldest first, never
    beyond what's owed. Does not commit."""
    rows = _approved_allocations(db, [employee_id]).get(employee_id, [])
    allocation_ids = [a.id for a in rows]

    if allocation_ids:
        db.query(TripChargeDeductionLog).filter(
            TripChargeDeductionLog.allocation_id.in_(allocation_ids),
            TripChargeDeductionLog.payroll_cutoff_period == cutoff_period,
        ).delete(synchronize_session=False)

    other, _ = _deducted(db, allocation_ids, cutoff_period)
    remaining = {
        a.id: max(_money(a.amount) - other[a.id], Decimal("0")) for a in rows
    }
    take = defaultdict(Decimal)
    left = max(_money(amount), Decimal("0"))

    # First each charge's own per-pay amount, then anything extra HR entered
    # goes to the oldest charge first.
    for allocation in rows:
        share = min(_per_pay(allocation, remaining[allocation.id]), left)
        take[allocation.id] += share
        left -= share
    for allocation in rows:
        extra = min(remaining[allocation.id] - take[allocation.id], left)
        take[allocation.id] += extra
        left -= extra

    for allocation in rows:
        if take[allocation.id] > 0:
            db.add(
                TripChargeDeductionLog(
                    allocation_id=allocation.id,
                    amount=take[allocation.id],
                    payroll_cutoff_period=cutoff_period,
                    recorded_by_user_id=user_id,
                )
            )

    applied = sum(take.values(), Decimal("0"))
    balance_after = sum(remaining.values(), Decimal("0")) - applied
    return {"applied": float(applied), "balance_after": float(balance_after)}
