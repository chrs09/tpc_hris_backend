import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlalchemy.orm import Session

from app.utils.response import api_response

from app.services.file_service import FileService
from app.core.database import get_db
from app.core.config import Settings
from app.core.dependencies import get_current_user
from app.models.applicant_remarks import ApplicantRemark
from app.models.applicants import Applicant
from app.models.employees import Employee
from app.models.employee_family import EmployeeFamilyDetails
from app.models.employee_government import EmployeeGovernmentDetails
from app.models.employee_emergency import EmployeeEmergencyContact
from app.models.employee_education import EmployeeEducation
from app.models.employee_employment import EmployeeEmploymentHistory
from app.models.employee_reference import EmployeeReference
from app.models.files import File as FileModel
from app.models.user import User
from app.models.employee_personal import EmployeePersonalDetails
from app.models.applicant_onboarding import ApplicantOnboarding
from app.models.applicant_education import ApplicantEducation
from app.models.applicant_references import ApplicantReference
from app.models.applicant_employment_history import ApplicantEmploymentHistory
from app.models.applicant_questions import ApplicantQuestion
from app.models.applicant_qresponse import ApplicantQResponse
from app.schemas.applicant import (
    ApplicantRemarkResponse,
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


def get_applicant_selfie_url(db: Session, applicant_id: int):
    selfie = (
        db.query(FileModel)
        .filter(
            FileModel.entity_type == "applicant",
            FileModel.entity_id == applicant_id,
            FileModel.document_type == "SELFIE_PHOTO",
        )
        .first()
    )
    return selfie.file_url if selfie else None


def serialize_onboarding(onboarding: ApplicantOnboarding | None):
    if not onboarding:
        return None

    return {
        "id": onboarding.id,
        "applicant_id": onboarding.applicant_id,
        "first_name": onboarding.first_name,
        "last_name": onboarding.last_name,
        "email": onboarding.email,
        "department": onboarding.department,
        "position": onboarding.position,
        "birthday": onboarding.birthday,
        "birthplace": onboarding.birthplace,
        "gender": onboarding.gender,
        "civil_status": onboarding.civil_status,
        "religion": onboarding.religion,
        "citizenship": onboarding.citizenship,
        "height": onboarding.height,
        "weight": onboarding.weight,
        "language": onboarding.language,
        "contact_number": onboarding.contact_number,
        "current_address": onboarding.current_address,
        "provincial_address": onboarding.provincial_address,
        "spouse_name": onboarding.spouse_name,
        "father_name": onboarding.father_name,
        "mother_name": onboarding.mother_name,
        "emergency_contact_name": onboarding.emergency_contact_name,
        "emergency_contact_number": onboarding.emergency_contact_number,
        "emergency_relationship": onboarding.emergency_relationship,
        "sss": onboarding.sss,
        "philhealth": onboarding.philhealth,
        "pagibig": onboarding.pagibig,
        "tin": onboarding.tin,
        "is_submitted": bool(onboarding.is_submitted),
        "submitted_at": onboarding.submitted_at,
        "reviewed_at": onboarding.reviewed_at,
        "created_at": onboarding.created_at,
        "updated_at": onboarding.updated_at,
        "current_salary": (
            float(onboarding.current_salary) if onboarding.current_salary else None
        ),
        "expected_salary": (
            float(onboarding.expected_salary) if onboarding.expected_salary else None
        ),
        "salary_type": onboarding.salary_type,
    }


def serialize_education(records):
    return [
        {
            "id": record.id,
            "applicant_id": record.applicant_id,
            "level": record.level,
            "institution": record.institution,
            "degree": record.degree,
            "year_from": record.year_from,
            "year_to": record.year_to,
            "skills": record.skills,
        }
        for record in records
    ]


def serialize_employment(records):
    return [
        {
            "id": record.id,
            "applicant_id": record.applicant_id,
            "company_name": record.company_name,
            "position": record.position,
            "date_from": record.date_from,
            "date_to": record.date_to,
            "reason_for_leaving": record.reason_for_leaving,
            "salary_history": (
                float(record.salary_history) if record.salary_history else None
            ),
            "salary_type": record.salary_type,
        }
        for record in records
    ]


def serialize_references(records):
    return [
        {
            "id": record.id,
            "applicant_id": record.applicant_id,
            "name": record.name,
            "position": record.position,
            "address": record.address,
            "contact": record.contact,
        }
        for record in records
    ]


def serialize_questions(records):
    return [
        {
            "id": record.id,
            "question_key": record.question_key,
            "question_text": record.question_text,
            "question_type": record.question_type,
            "is_required": record.is_required,
            "sort_order": record.sort_order,
        }
        for record in records
    ]


def serialize_question_responses(records, question_map: dict[int, str]):
    return [
        {
            "id": record.id,
            "applicant_id": record.applicant_id,
            "question_id": record.question_id,
            "question_key": question_map.get(record.question_id),
            "answer_text": record.answer_text,
        }
        for record in records
    ]


def normalize_position(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.lower().strip().split())


def infer_role_from_position(position: str | None) -> str:
    normalized = normalize_position(position)

    if "helper" in normalized:
        return "helper"

    if "driver" in normalized:
        return "driver"

    return "admin"


def filter_questions_by_position(questions, position: str | None):
    role = infer_role_from_position(position)

    if role == "helper":
        return [
            question
            for question in questions
            if question.question_key.startswith("helper_")
        ]

    if role == "driver":
        return [
            question
            for question in questions
            if not question.question_key.startswith("admin_")
            and not question.question_key.startswith("helper_")
        ]

    return [
        question for question in questions if question.question_key.startswith("admin_")
    ]


def get_remark_image_url(db: Session, remark_id: int):
    image = (
        db.query(FileModel)
        .filter(
            FileModel.entity_type == "applicant_remark",
            FileModel.entity_id == remark_id,
            FileModel.document_type == "REMARK_IMAGE",
        )
        .order_by(FileModel.created_at.desc())
        .first()
    )
    return image.file_url if image else None


def serialize_remark(db: Session, remark: ApplicantRemark):
    return {
        "id": remark.id,
        "applicant_id": remark.applicant_id,
        "status": remark.status,
        "remark": remark.remark,
        "created_at": remark.created_at,
        "created_by_user_id": remark.created_by_user_id,
        "image_url": get_remark_image_url(db, remark.id),
    }


@router.get("/")
def get_applicants(db: Session = Depends(get_db)):
    applicants = db.query(Applicant).order_by(Applicant.created_at.desc()).all()

    result = []
    for applicant in applicants:
        onboarding = (
            db.query(ApplicantOnboarding)
            .filter(ApplicantOnboarding.applicant_id == applicant.id)
            .first()
        )

        result.append(
            {
                "id": applicant.id,
                "first_name": applicant.first_name,
                "middle_name": applicant.middle_name,
                "last_name": applicant.last_name,
                "suffix": applicant.suffix,
                "email": applicant.email,
                "contact_number": applicant.contact_number,
                "position_applied": applicant.position_applied,
                "status": applicant.status,
                "created_at": applicant.created_at,
                "cv_url": get_applicant_cv_url(db, applicant.id),
                "selfie_photo_url": get_applicant_selfie_url(db, applicant.id),
                "is_converted_to_employee": applicant.is_converted_to_employee,
                "employee_id": applicant.employee_id,
                "hired_at": applicant.hired_at,
                "converted_at": applicant.converted_at,
                "onboarding_is_submitted": bool(onboarding and onboarding.is_submitted),
                "onboarding_submitted_at": (
                    onboarding.submitted_at if onboarding else None
                ),
            }
        )

    return api_response(result)


@router.get("/{applicant_id}")
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

    onboarding = (
        db.query(ApplicantOnboarding)
        .filter(ApplicantOnboarding.applicant_id == applicant.id)
        .first()
    )

    serialized_remarks = [serialize_remark(db, remark) for remark in remarks]

    response = {
        "id": applicant.id,
        "first_name": applicant.first_name,
        "middle_name": applicant.middle_name,
        "last_name": applicant.last_name,
        "suffix": applicant.suffix,
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
        "onboarding_is_submitted": bool(onboarding and onboarding.is_submitted),
        "onboarding_submitted_at": (onboarding.submitted_at if onboarding else None),
        "remarks": serialized_remarks,
    }

    return api_response(response)


@router.get("/{applicant_id}/onboarding")
def get_applicant_onboarding(
    applicant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ["admin", "superadmin", "hr"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    applicant = db.query(Applicant).filter(Applicant.id == applicant_id).first()

    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    onboarding = (
        db.query(ApplicantOnboarding)
        .filter(ApplicantOnboarding.applicant_id == applicant.id)
        .first()
    )

    if not onboarding:
        raise HTTPException(
            status_code=404,
            detail="Applicant onboarding form not found",
        )

    education_records = (
        db.query(ApplicantEducation)
        .filter(ApplicantEducation.applicant_id == applicant.id)
        .order_by(ApplicantEducation.id.asc())
        .all()
    )

    employment_history = (
        db.query(ApplicantEmploymentHistory)
        .filter(ApplicantEmploymentHistory.applicant_id == applicant.id)
        .order_by(ApplicantEmploymentHistory.id.asc())
        .all()
    )

    references = (
        db.query(ApplicantReference)
        .filter(ApplicantReference.applicant_id == applicant.id)
        .order_by(ApplicantReference.id.asc())
        .all()
    )

    all_questions = (
        db.query(ApplicantQuestion)
        .filter(ApplicantQuestion.is_active.is_(True))
        .order_by(ApplicantQuestion.sort_order.asc(), ApplicantQuestion.id.asc())
        .all()
    )

    filtered_questions = filter_questions_by_position(
        all_questions,
        applicant.position_applied,
    )

    question_responses = (
        db.query(ApplicantQResponse)
        .filter(ApplicantQResponse.applicant_id == applicant.id)
        .order_by(ApplicantQResponse.id.asc())
        .all()
    )

    question_id_to_key = {
        question.id: question.question_key for question in all_questions
    }

    return {
        "applicant": {
            "id": applicant.id,
            "first_name": applicant.first_name,
            "last_name": applicant.last_name,
            "email": applicant.email,
            "contact_number": applicant.contact_number,
            "position_applied": applicant.position_applied,
            "status": applicant.status,
            "cv_url": get_applicant_cv_url(db, applicant.id),
            "onboarding_submitted_at": applicant.onboarding_submitted_at,
            "onboarding_is_submitted": bool(onboarding.is_submitted),
        },
        "onboarding": serialize_onboarding(onboarding),
        "education_records": serialize_education(education_records),
        "employment_history": serialize_employment(employment_history),
        "references": serialize_references(references),
        "questions": serialize_questions(filtered_questions),
        "question_responses": serialize_question_responses(
            question_responses,
            question_id_to_key,
        ),
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
    remark: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    applicant = db.query(Applicant).filter(Applicant.id == applicant_id).first()

    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    cleaned_remark = remark.strip() if remark else ""

    if not cleaned_remark and not image:
        raise HTTPException(
            status_code=400,
            detail="Remark or image is required",
        )

    if image and (
        not image.content_type or not image.content_type.startswith("image/")
    ):
        raise HTTPException(status_code=400, detail="Only image files are allowed")

    new_remark = ApplicantRemark(
        applicant_id=applicant_id,
        status=status or applicant.status,
        remark=cleaned_remark if cleaned_remark else None,
        created_by_user_id=current_user.id,
    )

    db.add(new_remark)
    db.commit()
    db.refresh(new_remark)

    if image:
        file_service = FileService()
        file_url = file_service.upload(image, f"applicant_remarks/{new_remark.id}")

        db.add(
            FileModel(
                entity_type="applicant_remark",
                entity_id=new_remark.id,
                document_type="REMARK_IMAGE",
                file_url=file_url,
                uploaded_by=current_user.id,
            )
        )
        db.commit()

    return serialize_remark(db, new_remark)


@router.post("/{applicant_id}/generate-employment-form")
def generate_employment_form(
    applicant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ["admin", "superadmin", "hr"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    applicant = db.query(Applicant).filter(Applicant.id == applicant_id).first()

    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    if applicant.status.lower() != "interview":
        raise HTTPException(
            status_code=400,
            detail="Employment form can only be generated for interview applicants",
        )

    if applicant.is_converted_to_employee:
        raise HTTPException(
            status_code=400,
            detail="Applicant has already been converted to employee",
        )

    token = secrets.token_urlsafe(32)

    applicant.onboarding_token = token
    applicant.onboarding_token_expires_at = datetime.utcnow() + timedelta(days=7)
    applicant.onboarding_link_sent_at = datetime.utcnow()

    db.commit()
    db.refresh(applicant)

    form_url = f"{Settings.FRONTEND_URL.rstrip('/')}/tytan-onboarding-form/{token}"

    return {
        "message": "Employment form link generated successfully",
        "form_url": form_url,
        "expires_at": applicant.onboarding_token_expires_at,
    }


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
        db.query(Employee).filter(Employee.email == applicant.email).first()
    )
    if existing_employee:
        raise HTTPException(
            status_code=400,
            detail="An employee with this email already exists",
        )

    onboarding = (
        db.query(ApplicantOnboarding)
        .filter(ApplicantOnboarding.applicant_id == applicant.id)
        .first()
    )

    if not onboarding:
        raise HTTPException(
            status_code=400,
            detail="Applicant onboarding form not found",
        )

    if not onboarding.is_submitted:
        raise HTTPException(
            status_code=400,
            detail="Applicant onboarding form must be submitted before conversion",
        )

    department = payload.department.strip() if payload.department else ""
    if not department:
        raise HTTPException(status_code=400, detail="Department is required")

    position = (
        payload.position.strip()
        if payload.position and payload.position.strip()
        else (onboarding.position or applicant.position_applied)
    )

    if not position:
        raise HTTPException(status_code=400, detail="Position is required")

    education_records = (
        db.query(ApplicantEducation)
        .filter(ApplicantEducation.applicant_id == applicant.id)
        .order_by(ApplicantEducation.id.asc())
        .all()
    )

    employment_records = (
        db.query(ApplicantEmploymentHistory)
        .filter(ApplicantEmploymentHistory.applicant_id == applicant.id)
        .order_by(ApplicantEmploymentHistory.id.asc())
        .all()
    )

    employee_references = (
        db.query(ApplicantReference)
        .filter(ApplicantReference.applicant_id == applicant.id)
        .order_by(ApplicantReference.id.asc())
        .all()
    )

    try:
        # 1. Create base employee
        new_employee = Employee(
            first_name=onboarding.first_name or applicant.first_name,
            last_name=onboarding.last_name or applicant.last_name,
            email=onboarding.email or applicant.email,
            position=position,
            department=department,
            is_active=1,
            is_available=1,
            created_by_user_id=current_user.id,
            date_hired=onboarding.date_hired or datetime.utcnow().date(),
        )
        db.add(new_employee)
        db.flush()  # needed to get new_employee.id

        # 2. Personal details
        personal_details = EmployeePersonalDetails(
            employee_id=new_employee.id,
            birthday=onboarding.birthday,
            birthplace=onboarding.birthplace,
            gender=onboarding.gender,
            civil_status=onboarding.civil_status,
            religion=onboarding.religion,
            citizenship=onboarding.citizenship,
            height=onboarding.height,
            weight=onboarding.weight,
            language=onboarding.language,
            contact_number=onboarding.contact_number or applicant.contact_number,
            current_address=onboarding.current_address,
            provincial_address=onboarding.provincial_address,
        )
        db.add(personal_details)

        # 3. Family details
        family_details = EmployeeFamilyDetails(
            employee_id=new_employee.id,
            spouse_name=onboarding.spouse_name,
            father_name=onboarding.father_name,
            mother_name=onboarding.mother_name,
        )
        db.add(family_details)

        # 4. Government details
        government_details = EmployeeGovernmentDetails(
            employee_id=new_employee.id,
            sss_number=onboarding.sss,
            philhealth_number=onboarding.philhealth,
            pagibig_number=onboarding.pagibig,
            tin_number=onboarding.tin,
        )
        db.add(government_details)

        # 5. Emergency contact
        if (
            onboarding.emergency_contact_name
            or onboarding.emergency_contact_number
            or onboarding.emergency_relationship
        ):
            emergency_contact = EmployeeEmergencyContact(
                employee_id=new_employee.id,
                contact_name=onboarding.emergency_contact_name,
                contact_number=onboarding.emergency_contact_number,
                relationship_type=onboarding.emergency_relationship,
            )
            db.add(emergency_contact)

        # 6. Education records
        for record in education_records:
            db.add(
                EmployeeEducation(
                    employee_id=new_employee.id,
                    level=record.level,
                    institution=record.institution,
                    degree=record.degree,
                    year_from=record.year_from,
                    year_to=record.year_to,
                    skills=record.skills,
                )
            )

        # 7. Employment history
        for record in employment_records:
            db.add(
                EmployeeEmploymentHistory(
                    employee_id=new_employee.id,
                    company_name=record.company_name,
                    position=record.position,
                    date_from=record.date_from,
                    date_to=record.date_to,
                    reason_for_leaving=record.reason_for_leaving,
                    salary_history=record.salary_history,
                    salary_type=record.salary_type,
                )
            )

        # 8. References
        for record in employee_references:
            db.add(
                EmployeeReference(
                    employee_id=new_employee.id,
                    name=record.name,
                    contact=record.contact,
                    address=record.address,
                    position=record.position,
                )
            )
        # 9. Mark applicant as converted
        applicant.is_converted_to_employee = True
        applicant.employee_id = new_employee.id
        applicant.converted_at = datetime.utcnow()

        db.commit()
        db.refresh(new_employee)

        return {
            "message": "Applicant converted to employee successfully",
            "employee_id": new_employee.id,
            "employee": {
                "id": new_employee.id,
                "first_name": new_employee.first_name,
                "last_name": new_employee.last_name,
                "email": new_employee.email,
                "department": new_employee.department,
                "position": new_employee.position,
            },
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to convert applicant to employee: {str(e)}",
        )
