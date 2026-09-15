from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.user import User, UserRole
from app.models.employees import Employee
from app.models.user_revision import UserRevision
from app.core.security import hash_password


def create_user_service(data, db: Session):

    employee = db.query(Employee).filter(Employee.id == data.employee_id).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    if employee.user:
        raise HTTPException(
            status_code=400,
            detail="Employee already has account",
        )

    # Generate unique username
    base_username = employee.last_name.lower()
    username = base_username
    counter = 1

    while db.query(User).filter(User.username == username).first():
        username = f"{base_username}{counter}"
        counter += 1

    # Generate temporary password -- lowercase to keep it easy to type/read
    # off a printed sheet, and the account is never forced to change it
    # (must_change_password=False below), since re-issuing a new password
    # on every first login was adding hassle without a real security need
    # here.
    temporary_password = employee.last_name.lower() + str(datetime.now().year)

    new_user = User(
        username=username,
        email=employee.email,
        hashed_password=hash_password(temporary_password),
        role=UserRole(data.role.value),
        employee_id=employee.id,
        is_active=True,
        must_change_password=False,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user, temporary_password


def update_user_service(
    user_id: int,
    data,
    db: Session,
    changed_by_user_id: int = None,
    caller_is_superadmin: bool = True,
):
    """Applies role/is_active changes to a user and records each change in
    tpc_user_revisions (see app/models/user_revision.py) so it's traceable
    later who changed what, when, and (for deactivation) why.

    Required by: PATCH /users/{user_id} in app/api/users.py.
    """

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # PATCH /users/{user_id} is reachable either by a real superadmin or by
    # someone granted "administrator.users" via Module Assignment (see
    # require_role_or_module in app/api/users.py). A module grant must
    # never be usable to touch an existing superadmin's account or to
    # promote anyone to superadmin -- that would let a granted user
    # escalate themselves or lock out the real superadmin. Only an actual
    # superadmin caller may do either.
    if not caller_is_superadmin:
        if user.role == UserRole.SUPERADMIN:
            raise HTTPException(
                status_code=403,
                detail="Only a superadmin can modify a superadmin account.",
            )
        if data.role is not None and UserRole(data.role) == UserRole.SUPERADMIN:
            raise HTTPException(
                status_code=403,
                detail="Only a superadmin can grant the superadmin role.",
            )

    revisions = []

    if data.role is not None:
        new_role = UserRole(data.role)

        if new_role != user.role:
            revisions.append(
                UserRevision(
                    user_id=user.id,
                    field_changed="role",
                    old_value=user.role.value,
                    new_value=new_role.value,
                    reason=data.reason,
                    changed_by_user_id=changed_by_user_id,
                )
            )

        user.role = new_role

    if data.is_active is not None:
        # Deactivating a user must always come with a reason -- this is
        # what tpc_user_revisions.reason is for when field_changed is
        # "is_active" and new_value is "False".
        if user.is_active and not data.is_active and not (data.reason or "").strip():
            raise HTTPException(
                status_code=400,
                detail="A reason is required when deactivating a user.",
            )

        if data.is_active != user.is_active:
            revisions.append(
                UserRevision(
                    user_id=user.id,
                    field_changed="is_active",
                    old_value=str(user.is_active),
                    new_value=str(data.is_active),
                    reason=data.reason,
                    changed_by_user_id=changed_by_user_id,
                )
            )

        user.is_active = data.is_active

    for revision in revisions:
        db.add(revision)

    db.commit()
    db.refresh(user)

    return user


def get_user_revisions_service(user_id: int, db: Session):
    return (
        db.query(UserRevision)
        .filter(UserRevision.user_id == user_id)
        .order_by(UserRevision.created_at.desc())
        .all()
    )
