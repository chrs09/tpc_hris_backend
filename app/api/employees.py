from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.employees import Employee
from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeResponse
from app.models.user import User
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/employees", tags=["Employees"])


# ==============================
# Employee List (Only Active)
# ==============================
@router.get("/", response_model=list[EmployeeResponse])
def get_employees(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    employees = db.query(Employee).filter(Employee.is_active == 1).all()
    return employees


# ==============================
# Employee Detail (Only Active)
# ==============================
@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id, Employee.is_active == 1)
        .first()
    )

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    return employee


# ==============================
# Employee Create
# ==============================
@router.post("/", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
def create_employee(
    employee: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_employee = Employee(
        first_name=employee.first_name,
        last_name=employee.last_name,
        email=employee.email,
        position=employee.position,
        date_hired=employee.date_hired,
        department=employee.department,
        is_active=1,  # ALWAYS ACTIVE ON CREATE
        created_by_user_id=current_user.id,
    )

    db.add(new_employee)
    db.commit()
    db.refresh(new_employee)

    return new_employee


# ==============================
# Employee Update (Keep Active)
# ==============================
@router.put("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: int,
    employee: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing_employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id, Employee.is_active == 1)
        .first()
    )

    if not existing_employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    existing_employee.first_name = employee.first_name
    existing_employee.last_name = employee.last_name
    existing_employee.email = employee.email
    existing_employee.position = employee.position
    existing_employee.date_hired = employee.date_hired
    existing_employee.department = employee.department

    # FORCE ACTIVE (never allow update to deactivate)
    existing_employee.is_active = 1

    db.commit()
    db.refresh(existing_employee)

    return existing_employee


# ==============================
# Employee Soft Delete
# ==============================
@router.delete("/{employee_id}")
def delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    if employee.is_active == 0:
        raise HTTPException(status_code=400, detail="Employee already inactive")

    employee.is_active = 0  # SOFT DELETE
    db.commit()

    return {"message": "Employee successfully deactivated"}
