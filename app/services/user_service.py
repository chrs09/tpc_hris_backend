import secrets
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.user import User, UserRole
from app.models.employees import Employee
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

    # Generate temporary password
    temporary_password = employee.last_name.capitalize() + secrets.token_hex(3)

    new_user = User(
        username=username,
        email=employee.email,
        hashed_password=hash_password(temporary_password),
        role=UserRole(data.role.value),
        employee_id=employee.id,
        is_active=True,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user, temporary_password


def update_user_service(user_id: int, data, db: Session):

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent modifying superadmin account
    if user.role == UserRole.SUPERADMIN:
        raise HTTPException(status_code=400, detail="Cannot modify superadmin account")

    if data.role is not None:
        user.role = UserRole(data.role)

    if data.is_active is not None:
        user.is_active = data.is_active

    db.commit()
    db.refresh(user)

    return user
