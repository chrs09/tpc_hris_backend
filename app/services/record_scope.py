"""View all vs only their own, for modules that list records people
encode (e.g. Finance -> Expense).

Set per person on the Org Chart (What they can access): the grant's
"View all" toggle is stored as EmployeeModuleAccess.view_scope = "all".
Superadmins always see everything; everyone else sees only the records
they encoded unless their grant says "all".
"""

from sqlalchemy.orm import Session

from app.models.employee_module_access import EmployeeModuleAccess
from app.models.user import User


def sees_all_records(db: Session, user: User | None, module_key: str) -> bool:
    if not user:
        return False
    role = getattr(user.role, "value", user.role) or ""
    if role == "superadmin":
        return True
    if not user.employee_id:
        return False
    return (
        db.query(EmployeeModuleAccess.id)
        .filter(
            EmployeeModuleAccess.employee_id == user.employee_id,
            EmployeeModuleAccess.module_key == module_key,
            EmployeeModuleAccess.view_scope == "all",
        )
        .first()
        is not None
    )
