# app/services/approval_chain.py
#
# Org-chart approval routing for Cash Advance, Overtime and Attendance.
#
# Each org unit's head can be ticked as an approver per type (OrgUnit.
# approves). A request climbs the org chart from the employee's own unit
# and stops at every head who has that type ticked -- e.g. Motorpool ->
# Motorpool Head -> Admins: if both heads approve overtime, the Motorpool
# Head approves first and then it passes to the Admins head; if Admins
# has overtime unticked, the Motorpool Head's approval finishes it.
#
# A head's own request starts one layer up (nobody approves their own).
# An empty chain means "not set up on the org chart" -- callers then fall
# back to the old Reporting Hierarchy / superadmin behaviour.

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.employees import Employee
from app.models.org_unit import OrgUnit
from app.models.user import User
from app.utils.timezone import utc_to_ph
from app.utils.user_display import display_name

APPROVAL_KINDS = ("cash_advance", "overtime", "attendance")


def load_json_list(value) -> list:
    if not value:
        return []
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def unit_approves(unit: OrgUnit) -> set:
    return {k for k in load_json_list(unit.approves) if k in APPROVAL_KINDS}


def _role(user: User | None) -> str | None:
    if not user:
        return None
    return user.role.value if hasattr(user.role, "value") else str(user.role)


def _is_member(unit: OrgUnit, employee: Employee | None, user: User | None) -> bool:
    """Same membership rules the Org Chart page uses (org_chart.py)."""
    if employee is not None:
        if employee.id in {int(i) for i in load_json_list(unit.member_employee_ids)}:
            return True
        positions = {str(p).strip().lower() for p in load_json_list(unit.member_positions)}
        if (employee.position or "").strip().lower() in positions:
            return True
        if employee.department in set(load_json_list(unit.member_departments)):
            return True
    roles = {str(r).strip().lower() for r in load_json_list(unit.member_roles)}
    return bool(user is not None and (_role(user) or "").lower() in roles)


def _depth(unit: OrgUnit, by_id: dict) -> int:
    depth, seen, current = 0, set(), unit
    while current and current.parent_id and current.id not in seen:
        seen.add(current.id)
        current = by_id.get(current.parent_id)
        depth += 1
    return depth


def _deepest(units: list, by_id: dict):
    if not units:
        return None
    return sorted(units, key=lambda u: (-_depth(u, by_id), u.sort_order or 0, u.id))[0]


def resolve_chain(
    db: Session, employee: Employee | None, user: User | None, kind: str
) -> list[int]:
    """User ids who approve, in order, for this employee's request."""
    units = db.query(OrgUnit).all()
    if not units:
        return []
    by_id = {u.id: u for u in units}
    user_id = user.id if user else None

    # A head sits one layer above the people they lead.
    headed = [u for u in units if user_id and u.head_user_id == user_id]
    if headed:
        start_unit = _deepest(headed, by_id)
        current = by_id.get(start_unit.parent_id) if start_unit.parent_id else None
    else:
        current = _deepest([u for u in units if _is_member(u, employee, user)], by_id)

    chain: list[int] = []
    seen: set[int] = set()
    while current and current.id not in seen:
        seen.add(current.id)
        head = current.head_user_id
        if head and head != user_id and head not in chain and kind in unit_approves(current):
            chain.append(head)
        current = by_id.get(current.parent_id) if current.parent_id else None
    return chain


def my_approver_kinds(db: Session, user: User) -> dict:
    """Which types this user approves as an org chart head."""
    kinds = set()
    for unit in db.query(OrgUnit).filter(OrgUnit.head_user_id == user.id).all():
        kinds |= unit_approves(unit)
    return {k: k in kinds for k in APPROVAL_KINDS}


def dump_chain(chain: list[int]) -> str | None:
    return json.dumps(chain) if chain else None


def append_log(existing: str | None, user: User, action: str, remarks: str | None = None, **extra) -> str:
    log = load_json_list(existing)
    log.append(
        {
            "user_id": user.id,
            "name": display_name(user),
            "action": action,
            "remarks": remarks or None,
            "at": utc_to_ph(datetime.utcnow()).strftime("%Y-%m-%d %I:%M %p"),
            **extra,
        }
    )
    return json.dumps(log)


def describe_chain(db: Session, chain_json: str | None, step: int | None, log_json: str | None, status_done: bool) -> dict:
    """Progress for the UI: every approver with approved / current / waiting."""
    chain = [int(i) for i in load_json_list(chain_json)]
    if not chain:
        return {"approval_steps": [], "approval_log": load_json_list(log_json)}
    users = {
        u.id: u
        for u in db.query(User).filter(User.id.in_(chain)).all()
    }
    step = step or 0
    steps = []
    for index, uid in enumerate(chain):
        if index < step:
            state = "approved"
        elif index == step and not status_done:
            state = "current"
        elif status_done and index <= step:
            state = "done"
        else:
            state = "waiting"
        steps.append(
            {
                "user_id": uid,
                "name": display_name(users[uid]) if uid in users else f"User #{uid}",
                "state": state,
            }
        )
    return {
        "approval_steps": steps,
        "approval_step": step,
        "approval_total": len(chain),
        "approval_log": load_json_list(log_json),
    }
