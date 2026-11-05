"""Which payroll group an employee is paid in -- from their department,
plus their payroll type for groups that split a department (Admin
monthly / Admin daily). Same rule as the Payroll page (PayrollList.jsx
groupFor)."""

import json

from sqlalchemy.orm import Session

from app.models.payroll_group import PayrollGroup

PAY_BASES = ("fixed_monthly", "fixed_daily", "per_trip_driver", "per_trip_helper")
TRIP_BASES = ("per_trip_driver", "per_trip_helper")
PAYROLL_TYPES = ("Monthly", "Daily")


def departments_of(group: PayrollGroup) -> list[str]:
    try:
        value = json.loads(group.departments or "[]")
    except ValueError:
        return []
    return [str(d) for d in value if d]


def normalize_payroll_type(value) -> str:
    """Anything that isn't Monthly is paid daily."""
    return "Monthly" if str(value or "").strip().lower() == "monthly" else "Daily"


def active_groups(db: Session) -> list[PayrollGroup]:
    return (
        db.query(PayrollGroup)
        .filter(PayrollGroup.is_active.is_(True))
        .order_by(PayrollGroup.sort_order, PayrollGroup.name)
        .all()
    )


def group_for(groups, department, payroll_type) -> PayrollGroup | None:
    dept = str(department or "").strip().lower()
    if not dept:
        return None
    kind = normalize_payroll_type(payroll_type)
    for group in groups:
        if dept in (d.lower() for d in departments_of(group)) and (
            not group.payroll_type or group.payroll_type == kind
        ):
            return group
    return None


def payroll_key(db: Session, department, payroll_type) -> str | None:
    """The name payroll runs / cutoffs are stored under: the group, else
    the department itself (not in any group)."""
    group = group_for(active_groups(db), department, payroll_type)
    return group.name if group else department
