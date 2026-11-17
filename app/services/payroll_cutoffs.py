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


def employee_rule(db: Session, employee) -> PayrollCutoffRule | None:
    """This employee's cutoff rule: their payroll group's, else their
    department's (None = no rule set)."""
    from app.services.payroll_groups import payroll_key

    department = getattr(employee, "department", None)
    if not department:
        return None
    names = [payroll_key(db, department, getattr(employee, "payroll_type", None)), department]
    for name in names:
        rule = (
            db.query(PayrollCutoffRule)
            .filter(PayrollCutoffRule.department == name)
            .first()
        )
        if rule:
            return rule
    return None


def employee_cutoff(db: Session, employee, day: date) -> tuple[date, date]:
    """The cutoff `day` falls in for this employee: their payroll group's
    rule, else their department's."""
    return cutoff_containing(employee_rule(db, employee), day)


def _payout_on(year: int, month: int, day: int | None) -> date:
    """Day of a month, clamped; 0 / None = the last day (same as the web)."""
    if not day:
        return _month_end(year, month)
    return _safe_day(year, month, day)


def payout_date(rule: PayrollCutoffRule | None, start: date, end: date) -> date | None:
    """Payday of the cutoff start..end -- same maths as the web's
    cutoffRules.js. None when there's no rule (no payday set)."""
    if rule is None:
        return None
    if rule.schedule_type == "weekly":
        return end + timedelta(days=rule.payout_offset_days or 0)
    if rule.schedule_type == "monthly":
        return _payout_on(start.year, start.month, rule.first_payout_day)
    s1 = rule.first_start_day or 1
    if start.day == s1:
        # First cutoff of the month: paid that month.
        return _payout_on(start.year, start.month, rule.first_payout_day)
    # Second cutoff: paid the month after it starts.
    year, month = _add_months(start.year, start.month, 1)
    return _payout_on(year, month, rule.second_payout_day)


def recent_periods(rule: PayrollCutoffRule | None, today: date, count: int = 24) -> list[dict]:
    """Newest first, starting with the cutoff containing `today`:
    [{"from", "to", "payout", "label"}] -- dates as "YYYY-MM-DD"."""
    periods = []
    cursor = today
    for _ in range(count):
        start, end = cutoff_containing(rule, cursor)
        payout = payout_date(rule, start, end)
        label = f"{start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}"
        if payout:
            label += f" · Payday {payout.strftime('%b %d')}"
        periods.append(
            {
                "from": start.isoformat(),
                "to": end.isoformat(),
                "payout": payout.isoformat() if payout else None,
                "label": label,
            }
        )
        cursor = start - timedelta(days=1)
    return periods
