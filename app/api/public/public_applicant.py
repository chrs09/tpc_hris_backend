from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.applicants import Applicant
from app.models.files import File as FileModel
from app.services.file_service import FileService

router = APIRouter(prefix="/api/public", tags=["Public Applicants"])


@router.post("/apply")
def apply(
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    contact_number: str = Form(...),
    position_applied: str = Form(...),
    middle_name: str = Form(None),
    suffix: str = Form(None),
    cv: UploadFile = File(...),
    selfie_photo: UploadFile = File(...),  # new required selfie photo
    db: Session = Depends(get_db),
):
    try:
        # =========================
        # 1. CREATE APPLICANT
        # =========================
        applicant = Applicant(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            suffix=suffix,
            email=email,
            contact_number=contact_number,
            position_applied=position_applied,
            status="pending",
        )

        db.add(applicant)
        db.flush()  # get applicant.id before commit

        # =========================
        # 2. VALIDATE FILES
        # =========================
        if selfie_photo and (
            not selfie_photo.content_type
            or not selfie_photo.content_type.startswith("image/")
        ):
            raise HTTPException(
                status_code=400,
                detail="Selfie photo must be an image file",
            )

        # =========================
        # 3. SAVE FILES
        # =========================
        file_service = FileService()

        cv_url = file_service.upload(
            cv,
            f"applicants/{applicant.id}/cv",
        )

        selfie_photo_url = file_service.upload(
            selfie_photo,
            f"applicants/{applicant.id}/selfie",
        )

        # =========================
        # 4. STORE FILE METADATA
        # =========================
        db.add(
            FileModel(
                entity_type="applicant",
                entity_id=applicant.id,
                document_type="CV",
                file_url=cv_url,
                uploaded_by=None,
            )
        )

        db.add(
            FileModel(
                entity_type="applicant",
                entity_id=applicant.id,
                document_type="SELFIE_PHOTO",
                file_url=selfie_photo_url,
                uploaded_by=None,
            )
        )

        # =========================
        # 5. COMMIT
        # =========================
        db.commit()

        return {
            "message": "Application submitted successfully",
            "applicant_id": applicant.id,
            "cv_url": cv_url,
            "selfie_photo_url": selfie_photo_url,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
