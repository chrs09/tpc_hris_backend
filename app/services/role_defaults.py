"""Role default access (Administrator -> Role Access).

Who gets which module, in order:
  1. superadmin            -> everything
  2. custom access saved   -> only their own grants (Org Chart / Module
                              Assignment; Employee.has_custom_module_access)
  3. role configured here  -> the role's saved default modules
  4. otherwise             -> the built-in defaults in the code (each page's
                              / endpoint's `roles` list)

Saving a role's defaults applies at once to everyone with that role who
has no custom access, including people added later -- so a new
coordinator starts with exactly what the role should have.

Role defaults never count as an "editable grant" (has_editable_grant):
actions that are otherwise superadmin-only still need a person's own
grant, so ticking e.g. Attendance for a role doesn't let everyone in it
edit attendance.
"""

import json

from sqlalchemy.orm import Session

from app.models.role_module_default import RoleModuleDefault


# Actions that only ever come from a person's own grant (they're checked
# with has_editable_grant), so they can't be role defaults: payroll steps
# and approving trip charges.
PER_PERSON_KEYS = {
    "payroll.payroll_prepare",
    "payroll.payroll_approve",
    "payroll.payroll_release",
    "trip_management.trip_charges_approve",
}


def role_value(role) -> str | None:
    if role is None:
        return None
    return role.value if hasattr(role, "value") else str(role)


def _load(text: str | None) -> set[str]:
    try:
        data = json.loads(text or "[]")
    except (TypeError, ValueError):
        return set()
    return {str(k) for k in data} if isinstance(data, list) else set()


def get_role_defaults(db: Session, role) -> dict | None:
    """{"module_keys": set, "read_only_keys": set} for a configured role,
    else None (the role keeps the built-in defaults)."""
    value = role_value(role)
    if not value or value == "superadmin":
        return None
    row = db.get(RoleModuleDefault, value)
    if row is None:
        return None
    keys = _load(row.module_keys)
    return {"module_keys": keys, "read_only_keys": _load(row.read_only_keys) & keys}


def serialize_row(row: RoleModuleDefault) -> dict:
    keys = _load(row.module_keys)
    return {
        "role": row.role,
        "module_keys": sorted(keys),
        "read_only_keys": sorted(_load(row.read_only_keys) & keys),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "updated_by_user_id": row.updated_by_user_id,
    }
