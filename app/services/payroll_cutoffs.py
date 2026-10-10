"""The payroll cutoff a date falls in, from the department's rule (Payroll
Cutoffs page; see app/models/payroll_cutoff_rule.py). Same maths as the
web's src/utils/payroll/cutoffRules.js (periodContaining) -- keep them in
step. Used e.g. to let overtime be filed for any day of the current
cutoff (Motorpool: its week; Admin: its semi-monthly cutoff)."""

import calendar
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.payroll_cutoff_rule import PayrollCutoffRule


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _safe_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def cutoff_containing(rule: PayrollCutoffRule | None, day: date) -> tuple[date, date]:
    """(start, end) of the cutoff that contains `day`. No rule = the
    default semi-monthly 1-15 / 16-end."""
    schedule = rule.schedule_type if rule else "semi_monthly"

    if schedule == "weekly":
        week_start = rule.week_start_day or 0  # 0 = Sunday .. 6 = Saturday
        weekday = (day.weekday() + 1) % 7  # Python Monday=0 -> Sunday=0
        start = day - timedelta(days=(weekday - week_start) % 7)
        return start, start + timedelta(days=6)

    if schedule == "monthly":
        return date(day.year, day.month, 1), _month_end(day.year, day.month)

    s1 = (rule.first_start_day if rule else None) or 1
    s2 = (rule.second_start_day if rule else None) or 16
    if s1 <= day.day < s2:
        return _safe_day(day.year, day.month, s1), _safe_day(day.year, day.month, s2 - 1)
    # Second cutoff: s2 .. (s1 - 1) of the next month, or month end when s1 is 1.
    year, month = (day.year, day.month) if day.day >= s2 else _add_months(day.year, day.month, -1)
    start = _safe_day(year, month, s2)
    if s1 == 1:
        end = _month_end(year, month)
    else:
        ny, nm = _add_months(year, month, 1)
        end = _safe_day(ny, nm, s1 - 1)
    return start, end


def employee_cutoff(db: Session, employee, day: date) -> tuple[date, date]:
    """The cutoff `day` falls in for this employee's department."""
    department = getattr(employee, "department", None)
    rule = (
        db.query(PayrollCutoffRule)
        .filter(PayrollCutoffRule.department == department)
        .first()
        if department
        else None
    )
    return cutoff_containing(rule, day)
