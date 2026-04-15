import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.applicant_questions import ApplicantQuestion
from app.schemas.applicant_questions import (
    ApplicantQuestionCreate,
    ApplicantQuestionResponse,
    ApplicantQuestionUpdate,
)

router = APIRouter(prefix="/api/admin", tags=["Admin Applicant Questions"])


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_")


def validate_role_and_type(target_role: str, question_type: str):
    allowed_roles = {"admin", "driver", "helper", "all"}
    allowed_question_types = {"text", "textarea", "select", "date"}

    if target_role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail="Invalid target_role. Allowed values: admin, driver, helper, all",
        )

    if question_type not in allowed_question_types:
        raise HTTPException(
            status_code=400,
            detail="Invalid question_type. Allowed values: text, textarea, select, date",
        )


def get_next_sort_order(db: Session, target_role: str) -> int:
    role_start_map = {
        "driver": 1,
        "admin": 101,
        "helper": 201,
        "all": 301,
    }

    last_sort_order = (
        db.query(func.max(ApplicantQuestion.sort_order))
        .filter(ApplicantQuestion.target_role == target_role)
        .scalar()
    )

    if last_sort_order is not None:
        return last_sort_order + 1

    return role_start_map[target_role]


@router.get(
    "/applicant-questions",
    response_model=list[ApplicantQuestionResponse],
)
def list_applicant_questions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    questions = (
        db.query(ApplicantQuestion)
        .order_by(
            ApplicantQuestion.target_role.asc(),
            ApplicantQuestion.sort_order.asc(),
            ApplicantQuestion.id.asc(),
        )
        .all()
    )
    return questions


@router.post(
    "/applicant-questions",
    response_model=ApplicantQuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_applicant_question(
    payload: ApplicantQuestionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    target_role = payload.target_role.strip().lower()
    key_suffix = slugify(payload.key_suffix)
    question_type = payload.question_type.strip().lower()

    validate_role_and_type(target_role, question_type)

    question_key = f"{target_role}_{key_suffix}"

    existing = (
        db.query(ApplicantQuestion)
        .filter(ApplicantQuestion.question_key == question_key)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Question key already exists",
        )

    sort_order = (
        payload.sort_order
        if payload.sort_order is not None
        else get_next_sort_order(db, target_role)
    )

    question = ApplicantQuestion(
        target_role=target_role,
        question_key=question_key,
        question_text=payload.question_text.strip(),
        question_type=question_type,
        is_required=payload.is_required,
        sort_order=sort_order,
        is_active=payload.is_active,
        created_by_user_id=current_user.id,
    )

    db.add(question)
    db.commit()
    db.refresh(question)

    return question


@router.put(
    "/applicant-questions/{question_id}",
    response_model=ApplicantQuestionResponse,
)
def update_applicant_question(
    question_id: int,
    payload: ApplicantQuestionUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    question = (
        db.query(ApplicantQuestion).filter(ApplicantQuestion.id == question_id).first()
    )

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    old_target_role = question.target_role
    new_target_role = payload.target_role.strip().lower()
    question_type = payload.question_type.strip().lower()

    validate_role_and_type(new_target_role, question_type)

    question.target_role = new_target_role
    question.question_text = payload.question_text.strip()
    question.question_type = question_type
    question.is_required = payload.is_required
    question.is_active = payload.is_active

    if payload.sort_order is not None:
        question.sort_order = payload.sort_order
    elif old_target_role != new_target_role:
        question.sort_order = get_next_sort_order(db, new_target_role)

    db.commit()
    db.refresh(question)

    return question
