from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.applicant_remarks import ApplicantRemark
from app.models.applicants import Applicant
from app.models.employees import Employee
from app.models.files import File as FileModel
from app.models.user import User
from app.models.employee_personal import EmployeePersonalDetails
from app.schemas.applicant import (
    ApplicantDetailResponse,
    ApplicantRemarkCreate,
    ApplicantRemarkResponse,
    ApplicantResponse,
    ApplicantStatusUpdate,
    ConvertApplicantRequest,
)

router = APIRouter(prefix="/api/admin/applicants", tags=["Admin Applicants"])

ALLOWED_STATUSES = [
    "pending",
    "reviewed",
    "interview",
    "for_pooling",
    "hired",
    "rejected",
    "withdrawn",
    "no_show",
]


def get_applicant_cv_url(db: Session, applicant_id: int):
    cv = (
        db.query(FileModel)
        .filter(
            FileModel.entity_type == "applicant",
            FileModel.entity_id == applicant_id,
            FileModel.document_type == "CV",
        )
        .first()
    )
    return cv.file_url if cv else None


@router.get("/", response_model=List[ApplicantResponse])
def get_applicants(db: Session = Depends(get_db)):
    applicants = db.query(Applicant).order_by(Applicant.created_at.desc()).all()

    result = []
    for applicant in applicants:
        result.append(
            {
                "id": applicant.id,
                "first_name": applicant.first_name,
                "last_name": applicant.last_name,
                "email": applicant.email,
                "contact_number": applicant.contact_number,
                "position_applied": applicant.position_applied,
                "status": applicant.status,
                "created_at": applicant.created_at,
                "cv_url": get_applicant_cv_url(db, applicant.id),
                "is_converted_to_employee": applicant.is_converted_to_employee,
                "employee_id": applicant.employee_id,
                "hired_at": applicant.hired_at,
                "converted_at": applicant.converted_at,
            }
        )

    return result


@router.get("/{applicant_id}", response_model=ApplicantDetailResponse)
def get_applicant_detail(applicant_id: int, db: Session = Depends(get_db)):
    applicant = db.query(Applicant).filter(Applicant.id == applicant_id).first()

    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    remarks = (
        db.query(ApplicantRemark)
        .filter(ApplicantRemark.applicant_id == applicant_id)
        .order_by(ApplicantRemark.created_at.desc())
        .all()
    )

    return {
        "id": applicant.id,
        "first_name": applicant.first_name,
        "last_name": applicant.last_name,
        "email": applicant.email,
        "contact_number": applicant.contact_number,
        "position_applied": applicant.position_applied,
        "status": applicant.status,
        "created_at": applicant.created_at,
        "cv_url": get_applicant_cv_url(db, applicant.id),
        "is_converted_to_employee": applicant.is_converted_to_employee,
        "employee_id": applicant.employee_id,
        "hired_at": applicant.hired_at,
        "converted_at": applicant.converted_at,
        "remarks": remarks,
    }


@router.patch("/{applicant_id}/status")
def update_applicant_status(
    applicant_id: int,
    payload: ApplicantStatusUpdate,
    db: Session = Depends(get_db),
):
    if payload.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    applicant = db.query(Applicant).filter(Applicant.id == applicant_id).first()

    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    old_status = applicant.status
    applicant.status = payload.status

    if payload.status == "hired" and applicant.hired_at is None:
        applicant.hired_at = datetime.utcnow()

    if old_status == "hired" and payload.status != "hired":
        applicant.hired_at = None

    db.commit()
    db.refresh(applicant)

    return {
        "message": "Applicant status updated successfully",
        "id": applicant.id,
        "status": applicant.status,
        "hired_at": applicant.hired_at,
    }


@router.post("/{applicant_id}/remarks", response_model=ApplicantRemarkResponse)
def add_applicant_remark(
    applicant_id: int,
    payload: ApplicantRemarkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    applicant = db.query(Applicant).filter(Applicant.id == applicant_id).first()

    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    if not payload.remark.strip():
        raise HTTPException(status_code=400, detail="Remark cannot be empty")

    remark = ApplicantRemark(
        applicant_id=applicant_id,
        status=payload.status or applicant.status,
        remark=payload.remark.strip(),
        created_by_user_id=current_user.id,
    )

    db.add(remark)
    db.commit()
    db.refresh(remark)

    return remark


@router.post("/{applicant_id}/convert-to-employee")
def convert_to_employee(
    applicant_id: int,
    payload: ConvertApplicantRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ["admin", "superadmin", "hr"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    applicant = db.query(Applicant).filter(Applicant.id == applicant_id).first()

    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    if applicant.status.lower() != "hired":
        raise HTTPException(
            status_code=400,
            detail="Only hired applicants can be converted to employee",
        )

    if applicant.is_converted_to_employee:
        raise HTTPException(
            status_code=400,
            detail="Applicant has already been converted to employee",
        )

    existing_employee = (
        db.query(Employee)
        .filter(Employee.email == applicant.email)
        .first()
    )

    if existing_employee:
        raise HTTPException(
            status_code=400,
            detail="An employee with this email already exists",
        )

    department = payload.department.strip()
    if not department:
        raise HTTPException(status_code=400, detail="Department is required")

    position = (
        payload.position.strip()
        if payload.position and payload.position.strip()
        else applicant.position_applied
    )

    new_employee = Employee(
        first_name=applicant.first_name,
        last_name=applicant.last_name,
        email=applicant.email,
        # contact_number=applicant.contact_number,
        position=position,
        department=department,
        is_active=1,
        is_available=1,
        # employment_status="active",
        created_by_user_id = current_user.id,
        date_hired=datetime.utcnow(),
    )

    db.add(new_employee)
    db.flush()

    personal_details = EmployeePersonalDetails(
        employee_id=new_employee.id,
        contact_number=applicant.contact_number,
    )
    db.add(personal_details)

    applicant.is_converted_to_employee = True
    applicant.employee_id = new_employee.id
    applicant.converted_at = datetime.utcnow()

    db.commit()
    db.refresh(new_employee)

    return {
        "message": "Applicant converted to employee successfully",
        "employee_id": new_employee.id,
    }