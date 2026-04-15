from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.applicant_questions import ApplicantQuestion

router = APIRouter(prefix="/api/public", tags=["Public Applicant Questions"])


@router.get("/applicant-questions")
def get_applicant_questions(
    role: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(ApplicantQuestion).filter(ApplicantQuestion.is_active.is_(True))

    if role:
        query = query.filter(ApplicantQuestion.target_role.in_([role.lower(), "all"]))

    questions = query.order_by(
        ApplicantQuestion.sort_order.asc(), ApplicantQuestion.id.asc()
    ).all()

    return [
        {
            "id": question.id,
            "question_key": question.question_key,
            "question_text": question.question_text,
            "question_type": question.question_type,
            "is_required": question.is_required,
            "sort_order": question.sort_order,
            "target_role": question.target_role,
        }
        for question in questions
    ]
