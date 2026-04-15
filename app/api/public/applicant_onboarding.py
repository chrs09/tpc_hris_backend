from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.applicant_qresponse import ApplicantQResponse
from app.models.applicant_questions import ApplicantQuestion
from app.models.applicants import Applicant
from app.models.applicant_onboarding import ApplicantOnboarding
from app.models.applicant_education import ApplicantEducation
from app.models.applicant_employment_history import ApplicantEmploymentHistory
from app.models.applicant_references import ApplicantReference
from app.schemas.applicant_onboarding import ApplicantOnboardingPayload

router = APIRouter(
    prefix="/api/public/applicant-onboarding",
    tags=["Public Applicant Onboarding"],
)


def get_valid_applicant_by_token(db: Session, token: str) -> Applicant:
    applicant = db.query(Applicant).filter(Applicant.onboarding_token == token).first()

    if not applicant:
        raise HTTPException(status_code=404, detail="Invalid onboarding link")

    if not applicant.onboarding_token_expires_at:
        raise HTTPException(status_code=400, detail="Onboarding link is not active")

    if applicant.onboarding_token_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Onboarding link has expired")

    if applicant.status not in ["interview", "onboarding", "hired"]:
        raise HTTPException(
            status_code=400,
            detail="Applicant is not allowed to access the onboarding form",
        )

    if applicant.is_converted_to_employee:
        raise HTTPException(
            status_code=400,
            detail="Applicant has already been converted to employee",
        )

    return applicant


def parse_salary(value):
    if value is None:
        return None

    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))

    cleaned = str(value).replace(",", "").strip()

    if cleaned == "":
        return None

    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid salary value: {value}",
        )


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
        "current_salary": (
            str(onboarding.current_salary)
            if onboarding.current_salary is not None
            else None
        ),
        "expected_salary": (
            str(onboarding.expected_salary)
            if onboarding.expected_salary is not None
            else None
        ),
        "salary_type": onboarding.salary_type,
        "sss": onboarding.sss,
        "philhealth": onboarding.philhealth,
        "pagibig": onboarding.pagibig,
        "tin": onboarding.tin,
        "is_submitted": bool(onboarding.is_submitted),
        "submitted_at": onboarding.submitted_at,
        "reviewed_at": onboarding.reviewed_at,
        "created_at": onboarding.created_at,
        "updated_at": onboarding.updated_at,
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
                str(record.salary_history)
                if record.salary_history is not None
                else None
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


@router.get("/{token}")
def get_onboarding_form(
    token: str,
    db: Session = Depends(get_db),
):
    applicant = get_valid_applicant_by_token(db, token)

    onboarding = (
        db.query(ApplicantOnboarding)
        .filter(ApplicantOnboarding.applicant_id == applicant.id)
        .first()
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
            "onboarding_submitted_at": applicant.onboarding_submitted_at,
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


@router.post("/{token}")
def save_onboarding_form(
    token: str,
    payload: ApplicantOnboardingPayload,
    db: Session = Depends(get_db),
):
    applicant = get_valid_applicant_by_token(db, token)

    onboarding = (
        db.query(ApplicantOnboarding)
        .filter(ApplicantOnboarding.applicant_id == applicant.id)
        .first()
    )

    if not onboarding:
        onboarding = ApplicantOnboarding(applicant_id=applicant.id)
        db.add(onboarding)
        db.flush()

    onboarding.first_name = payload.first_name
    onboarding.last_name = payload.last_name
    onboarding.email = payload.email
    onboarding.department = payload.department
    onboarding.position = payload.position

    onboarding.birthday = payload.birthday
    onboarding.birthplace = payload.birthplace
    onboarding.gender = payload.gender
    onboarding.civil_status = payload.civil_status
    onboarding.religion = payload.religion
    onboarding.citizenship = payload.citizenship
    onboarding.height = payload.height
    onboarding.weight = payload.weight
    onboarding.language = payload.language
    onboarding.contact_number = payload.contact_number
    onboarding.current_address = payload.current_address
    onboarding.provincial_address = payload.provincial_address

    onboarding.spouse_name = payload.spouse_name
    onboarding.father_name = payload.father_name
    onboarding.mother_name = payload.mother_name

    onboarding.emergency_contact_name = payload.emergency_contact_name
    onboarding.emergency_contact_number = payload.emergency_contact_number
    onboarding.emergency_relationship = payload.emergency_relationship

    onboarding.current_salary = parse_salary(payload.current_salary)
    onboarding.expected_salary = parse_salary(payload.expected_salary)
    onboarding.salary_type = payload.salary_type

    onboarding.sss = payload.sss
    onboarding.philhealth = payload.philhealth
    onboarding.pagibig = payload.pagibig
    onboarding.tin = payload.tin

    db.query(ApplicantEducation).filter(
        ApplicantEducation.applicant_id == applicant.id
    ).delete()

    for record in payload.education_records:
        db.add(
            ApplicantEducation(
                applicant_id=applicant.id,
                level=record.level,
                institution=record.institution,
                degree=record.degree,
                year_from=record.year_from,
                year_to=record.year_to,
                skills=record.skills,
            )
        )

    db.query(ApplicantEmploymentHistory).filter(
        ApplicantEmploymentHistory.applicant_id == applicant.id
    ).delete()

    for record in payload.employment_history:
        db.add(
            ApplicantEmploymentHistory(
                applicant_id=applicant.id,
                company_name=record.company_name,
                position=record.position,
                date_from=record.date_from,
                date_to=record.date_to,
                reason_for_leaving=record.reason_for_leaving,
                salary_history=parse_salary(record.salary_history),
                salary_type=record.salary_type,
            )
        )

    db.query(ApplicantReference).filter(
        ApplicantReference.applicant_id == applicant.id
    ).delete()

    for record in payload.references:
        db.add(
            ApplicantReference(
                applicant_id=applicant.id,
                name=record.name,
                position=record.position,
                address=record.address,
                contact=record.contact,
            )
        )

    db.query(ApplicantQResponse).filter(
        ApplicantQResponse.applicant_id == applicant.id
    ).delete()

    if payload.question_responses:
        question_map = {
            question.question_key: question.id
            for question in db.query(ApplicantQuestion)
            .filter(ApplicantQuestion.is_active.is_(True))
            .all()
        }

        for response in payload.question_responses:
            question_id = question_map.get(response.question_key)

            if not question_id:
                continue

            db.add(
                ApplicantQResponse(
                    applicant_id=applicant.id,
                    question_id=question_id,
                    answer_text=response.answer_text,
                )
            )

    db.commit()
    db.refresh(onboarding)

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

    question_response = (
        db.query(ApplicantQResponse)
        .filter(ApplicantQResponse.applicant_id == applicant.id)
        .order_by(ApplicantQResponse.id.asc())
        .all()
    )

    question_id_to_key = {
        question.id: question.question_key
        for question in db.query(ApplicantQuestion)
        .filter(ApplicantQuestion.is_active.is_(True))
        .all()
    }

    return {
        "message": "Onboarding form saved successfully.",
        "onboarding": serialize_onboarding(onboarding),
        "education_records": serialize_education(education_records),
        "employment_history": serialize_employment(employment_history),
        "references": serialize_references(references),
        "question_responses": serialize_question_responses(
            question_response,
            question_id_to_key,
        ),
    }


@router.post("/{token}/submit")
def submit_onboarding_form(
    token: str,
    db: Session = Depends(get_db),
):
    applicant = get_valid_applicant_by_token(db, token)

    onboarding = (
        db.query(ApplicantOnboarding)
        .filter(ApplicantOnboarding.applicant_id == applicant.id)
        .first()
    )

    if not onboarding:
        raise HTTPException(
            status_code=400,
            detail="No onboarding form found to submit",
        )

    required_fields = {
        "first_name": onboarding.first_name,
        "last_name": onboarding.last_name,
        "email": onboarding.email,
        "contact_number": onboarding.contact_number,
        "current_address": onboarding.current_address,
    }

    missing_fields = [key for key, value in required_fields.items() if not value]

    if missing_fields:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Please complete required fields before submitting.",
                "missing_fields": missing_fields,
            },
        )

    onboarding.is_submitted = True
    onboarding.submitted_at = datetime.utcnow()
    applicant.onboarding_submitted_at = datetime.utcnow()

    db.commit()

    return {
        "message": "Onboarding form submitted successfully.",
        "submitted_at": onboarding.submitted_at,
    }
