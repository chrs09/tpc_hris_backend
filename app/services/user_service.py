from sqlalchemy import func
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


def bulk_create_users_service(db: Session):
    """Creates a User account for every active employee that doesn't
    already have one, following the exact username/password conventions
    of create_user_service above (lastname-based username, deduped with a
    counter; lastname+year temporary password). Every new account is
    role=EMPLOYEE -- anyone who needs a different role gets it changed
    afterward via the existing Edit User flow, same as a single manual
    create would require if the admin picked the wrong role.

    Email is optional -- login is by username, not email, so an employee
    with no email on file still gets an account (email left null). Never
    raises for a single bad employee record (missing last name, or an
    email already claimed by another account) -- those are collected
    into `failed` and reported back instead, so one bad row can't block
    everyone else's account from being created.
    """
    candidates = (
        db.query(Employee)
        .outerjoin(User, User.employee_id == Employee.id)
        .filter(Employee.is_active == 1, User.id.is_(None))
        .order_by(Employee.last_name.asc())
        .all()
    )

    # Tracked in memory (not just re-queried per row) because new users
    # created earlier in this same loop aren't committed/visible to the
    # DB yet.
    existing_usernames = {row[0] for row in db.query(User.username).all()}
    existing_emails = {row[0] for row in db.query(User.email).all() if row[0]}

    current_year = str(datetime.now().year)

    created = []
    failed = []

    for employee in candidates:
        full_name = f"{employee.first_name} {employee.last_name}".strip()

        if not employee.last_name or not employee.last_name.strip():
            failed.append({
                "employee_id": employee.id,
                "name": full_name,
                "reason": "Employee has no last name on file.",
            })
            continue

        if employee.email and employee.email in existing_emails:
            failed.append({
                "employee_id": employee.id,
                "name": full_name,
                "reason": "Email already used by another account.",
            })
            continue

        base_username = employee.last_name.lower().strip()
        username = base_username
        counter = 1
        while username in existing_usernames:
            username = f"{base_username}{counter}"
            counter += 1

        temporary_password = base_username + current_year

        new_user = User(
            username=username,
            email=employee.email,
            hashed_password=hash_password(temporary_password),
            role=UserRole.EMPLOYEE,
            employee_id=employee.id,
            is_active=True,
            must_change_password=False,
        )
        db.add(new_user)

        existing_usernames.add(username)
        if employee.email:
            existing_emails.add(employee.email)

        created.append({
            "employee_id": employee.id,
            "name": full_name,
            "username": username,
            "temporary_password": temporary_password,
        })

    if created:
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Failed to save bulk-created accounts.",
            )

    return {
        "total_candidates": len(candidates),
        "created": created,
        "failed": failed,
    }


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

    if data.username is not None:
        new_username = " ".join(data.username.split())
        if len(new_username) < 3 or len(new_username) > 50:
            raise HTTPException(
                status_code=400,
                detail="Username must be 3 to 50 characters.",
            )
        if new_username != user.username:
            taken = (
                db.query(User.id)
                .filter(
                    func.lower(User.username) == new_username.lower(),
                    User.id != user.id,
                )
                .first()
            )
            if taken:
                raise HTTPException(
                    status_code=400, detail="That username is already taken."
                )
            revisions.append(
                UserRevision(
                    user_id=user.id,
                    field_changed="username",
                    old_value=user.username,
                    new_value=new_username,
                    reason=data.reason,
                    changed_by_user_id=changed_by_user_id,
                )
            )
            user.username = new_username

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


def reset_user_password_service(
    user_id: int,
    db: Session,
    changed_by_user_id: int = None,
):
    """Resets a user's password to lastname + birthday (MMDDYYYY), or --
    only when the employee has no birthday in their 201 file --
    lastname + the current year (same as a new account's password).
    Easy for an admin to read off screen and relay to the employee.
    Never stores the plaintext password anywhere except the one-time
    return value, same as account creation."""

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    employee = user.employee

    if not employee or not employee.last_name or not employee.last_name.strip():
        raise HTTPException(
            status_code=400,
            detail="This account has no linked employee with a last name on file.",
        )

    birthday = (
        employee.personal_details.birthday if employee.personal_details else None
    )

    last_name = employee.last_name.lower().strip()
    if birthday:
        temporary_password = last_name + birthday.strftime("%m%d%Y")
    else:
        temporary_password = last_name + str(datetime.now().year)

    user.hashed_password = hash_password(temporary_password)
    user.must_change_password = False

    db.add(
        UserRevision(
            user_id=user.id,
            field_changed="password",
            # The actual password is never written to the audit trail --
            # only that a reset happened and who did it.
            old_value=None,
            new_value="reset",
            reason=None,
            changed_by_user_id=changed_by_user_id,
        )
    )

    db.commit()
    db.refresh(user)

    return user, temporary_password


def get_user_revisions_service(user_id: int, db: Session):
    return (
        db.query(UserRevision)
        .filter(UserRevision.user_id == user_id)
        .order_by(UserRevision.created_at.desc())
        .all()
    )
