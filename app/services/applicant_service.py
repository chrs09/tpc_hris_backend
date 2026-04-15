from sqlalchemy.orm import Session
from app.models.files import File as FileModel


def get_applicant_file_url(db: Session, applicant_id: int, document_type: str):
    file_record = (
        db.query(FileModel)
        .filter(
            FileModel.entity_type == "applicant",
            FileModel.entity_id == applicant_id,
            FileModel.document_type == document_type,
        )
        .order_by(FileModel.id.desc())
        .first()
    )
    return file_record.file_url if file_record else None


def serialize_applicant(db: Session, applicant):
    return {
        "id": applicant.id,
        "first_name": applicant.first_name,
        "last_name": applicant.last_name,
        "email": applicant.email,
        "contact_number": applicant.contact_number,
        "position_applied": applicant.position_applied,
        "status": applicant.status,
        "created_at": applicant.created_at,
        "cv_url": get_applicant_file_url(db, applicant.id, "CV"),
        "selfie_photo_url": get_applicant_file_url(db, applicant.id, "SELFIE_PHOTO"),
    }


def serialize_applicant_detail(db: Session, applicant, remarks=None, onboarding=None):
    return {
        "id": applicant.id,
        "first_name": applicant.first_name,
        "last_name": applicant.last_name,
        "email": applicant.email,
        "contact_number": applicant.contact_number,
        "position_applied": applicant.position_applied,
        "status": applicant.status,
        "created_at": applicant.created_at,
        "cv_url": get_applicant_file_url(db, applicant.id, "CV"),
        "selfie_photo_url": get_applicant_file_url(db, applicant.id, "SELFIE_PHOTO"),
        "remarks": remarks or [],
        "onboarding": onboarding,
    }