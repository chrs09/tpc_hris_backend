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
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.employees import Employee
from app.models.org_unit import OrgUnit
from app.models.user import User
from app.utils.timezone import utc_to_ph
from app.utils.user_display import display_name

APPROVAL_KINDS = ("cash_advance", "overtime", "attendance", "leave")


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


# =========================================================
# AWAY TODAY -- skip an approver who's absent / on leave
#
# While the approver whose turn it is is out today (attendance Absent or
# On Leave, or an approved leave covering today), the request moves to
# the next head up, who can approve straight away. The last approver is
# never skipped (there's no one above them).
# =========================================================
def _today_ph() -> date:
    return (datetime.utcnow() + timedelta(hours=8)).date()


def approver_away(db: Session, user_id: int, on_date: date | None = None) -> str | None:
    """"absent" / "on leave" when this approver is out that day, else None."""
    from app.models.attendance import AttendanceRecord
    from app.models.leave_request import LeaveRequest

    user = db.get(User, user_id)
    if not user or not user.employee_id:
        return None
    on_date = on_date or _today_ph()
    record = (
        db.query(AttendanceRecord.status)
        .filter(
            AttendanceRecord.employee_id == user.employee_id,
            AttendanceRecord.attendance_date == on_date,
        )
        .first()
    )
    if record and record[0] == "Absent":
        return "absent"
    if record and record[0] == "On Leave":
        return "on leave"
    leave = (
        db.query(LeaveRequest.id)
        .filter(
            LeaveRequest.employee_id == user.employee_id,
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= on_date,
            LeaveRequest.end_date >= on_date,
        )
        .first()
    )
    return "on leave" if leave else None


def effective_step(db: Session, chain: list[int], step: int | None) -> tuple[int, list]:
    """Whose turn it really is today: (index, [(skipped index, reason)])."""
    index = step or 0
    skipped = []
    while index < len(chain) - 1:
        reason = approver_away(db, chain[index])
        if not reason:
            break
        skipped.append((index, reason))
        index += 1
    return index, skipped


def acting_index(db: Session, chain: list[int], step: int | None, user_id: int):
    """Which step this user is approving as -- their own turn, or the turn
    passed to them because the approvers before them are out -- plus the
    skipped ones. None when it isn't their turn (e.g. a superadmin
    overriding)."""
    step = step or 0
    index, skipped = effective_step(db, chain, step)
    # Their own step, unless they're out today (then it's passed up and
    # they can't act on it -- see skipped_for()).
    if step < len(chain) and chain[step] == user_id and step == index:
        return step, []
    if index < len(chain) and chain[index] == user_id:
        return index, skipped
    return None, []


def skipped_for(db: Session, chain: list[int], step: int | None, user_id: int) -> str | None:
    """"absent" / "on leave" when this user's step was passed up because
    they're out today -- so they can see the request but not act on it."""
    _, skipped = effective_step(db, chain, step)
    for index, reason in skipped:
        if chain[index] == user_id:
            return reason
    return None


def log_skipped(db: Session, log_json: str | None, chain: list[int], skipped: list) -> str | None:
    """Adds a "skipped -- absent/on leave today" line per skipped approver."""
    for index, reason in skipped:
        user = db.get(User, chain[index])
        if user:
            log_json = append_log(log_json, user, "skipped", f"{reason} today")
    return log_json


def describe_chain(db: Session, chain_json: str | None, step: int | None, log_json: str | None, status_done: bool) -> dict:
    """Progress for the UI: every approver with approved / current /
    skipped (out today) / waiting, plus whose turn it really is."""
    chain = [int(i) for i in load_json_list(chain_json)]
    if not chain:
        return {"approval_steps": [], "approval_log": load_json_list(log_json)}
    users = {
        u.id: u
        for u in db.query(User).filter(User.id.in_(chain)).all()
    }
    step = step or 0
    current, skipped = (step, []) if status_done else effective_step(db, chain, step)
    skipped_reason = dict(skipped)
    name_of = lambda uid: display_name(users[uid]) if uid in users else f"User #{uid}"
    steps = []
    for index, uid in enumerate(chain):
        note = None
        if index < step:
            state = "approved"
        elif index in skipped_reason:
            state = "skipped"
            note = skipped_reason[index]
        elif index == current and not status_done:
            state = "current"
        elif status_done and index <= step:
            state = "done"
        else:
            state = "waiting"
        steps.append({"user_id": uid, "name": name_of(uid), "state": state, "note": note})
    away_note = None
    if skipped:
        away = ", ".join(f"{name_of(chain[i])} is {reason}" for i, reason in skipped)
        away_note = f"{away} today -- passed to {name_of(chain[current])}."
    return {
        "approval_steps": steps,
        "approval_step": step,
        "approval_total": len(chain),
        "approval_log": load_json_list(log_json),
        # Whose turn it really is today (after skipping anyone out).
        "current_approver_id": None if status_done else chain[current],
        "approver_away_note": away_note,
    }


# =========================================================
# TEAM SCOPE -- what an org chart head may see
#
# A head (any org unit with them as head_user_id) only sees the people
# in the units they head, plus every unit below those, plus themselves --
# on the Attendance list/grid and OT approvals. Superadmin and anyone who
# isn't a head see everyone, as before.
# =========================================================
def team_scope(db: Session, user: User | None) -> dict | None:
    """None = no limit. Otherwise {"employee_ids": set, "unit_names": [...]}."""
    if not user or (_role(user) or "").lower() == "superadmin":
        return None
    units = db.query(OrgUnit).all()
    headed = [u for u in units if u.head_user_id == user.id]
    if not headed:
        return None

    children: dict[int | None, list] = {}
    for unit in units:
        children.setdefault(unit.parent_id, []).append(unit)
    scope_units, stack, seen = [], list(headed), set()
    while stack:
        unit = stack.pop()
        if unit.id in seen:
            continue
        seen.add(unit.id)
        scope_units.append(unit)
        stack.extend(children.get(unit.id, []))

    employees = db.query(Employee).filter(Employee.is_active == 1).all()
    users_by_employee = {
        u.employee_id: u
        for u in db.query(User).filter(User.employee_id.isnot(None)).all()
    }
    ids = {
        emp.id
        for emp in employees
        if any(_is_member(unit, emp, users_by_employee.get(emp.id)) for unit in scope_units)
    }
    if user.employee_id:
        ids.add(user.employee_id)
    return {
        "employee_ids": ids,
        "unit_names": [u.name for u in headed],
    }


def can_view_all_payroll(db: Session, user: User | None) -> bool:
    """Payroll needs everyone's attendance: superadmin, the payroll roles,
    or anyone granted the Payroll module."""
    if not user:
        return False
    if (_role(user) or "").lower() in ("superadmin", "admin", "payroll_admin"):
        return True
    if not user.employee_id:
        return False
    from app.models.employee_module_access import EmployeeModuleAccess

    return (
        db.query(EmployeeModuleAccess.id)
        .join(Employee, Employee.id == EmployeeModuleAccess.employee_id)
        .filter(
            Employee.id == user.employee_id,
            Employee.has_custom_module_access.is_(True),
            EmployeeModuleAccess.module_key == "payroll.payroll",
        )
        .first()
        is not None
    )
