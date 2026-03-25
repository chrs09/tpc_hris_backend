from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user
from app.core.database import get_db
from app.models.applicants import Applicant
from app.models.applicant_remarks import ApplicantRemark
from app.models.files import File as FileModel
from app.models.user import User
from app.schemas.applicant import (
    ApplicantResponse,
    ApplicantStatusUpdate,
    ApplicantRemarkCreate,
    ApplicantRemarkResponse,
    ApplicantDetailResponse,
)

from typing import List

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
    applicants = (
        db.query(Applicant)
        .order_by(Applicant.created_at.desc())
        .all()
    )

    result = []
    for applicant in applicants:
        result.append({
            "id": applicant.id,
            "first_name": applicant.first_name,
            "last_name": applicant.last_name,
            "email": applicant.email,
            "contact_number": applicant.contact_number,
            "position_applied": applicant.position_applied,
            "status": applicant.status,
            "created_at": applicant.created_at,
            "cv_url": get_applicant_cv_url(db, applicant.id),
        })

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

    applicant.status = payload.status
    db.commit()
    db.refresh(applicant)

    return {
        "message": "Applicant status updated successfully",
        "id": applicant.id,
        "status": applicant.status,
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