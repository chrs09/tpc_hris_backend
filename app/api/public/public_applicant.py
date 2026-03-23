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
    cv: UploadFile = File(...),  # only CV required
    db: Session = Depends(get_db),
):
    try:
        # =========================
        # 1. CREATE APPLICANT
        # =========================
        applicant = Applicant(
            first_name=first_name,
            last_name=last_name,
            email=email,
            contact_number=contact_number,
            position_applied=position_applied,
            status="pending",
        )

        db.add(applicant)
        db.flush()  # 🔥 IMPORTANT: get applicant.id before commit

        # =========================
        # 2. SAVE FILE USING YOUR SYSTEM
        # =========================
        file_service = FileService()

        file_url = file_service.upload(
            cv,
            f"applicants/{applicant.id}"  # ✅ your structure
        )

        # =========================
        # 3. STORE FILE METADATA
        # =========================
        db.add(FileModel(
            entity_type="applicant",   # 🔥 KEY DIFFERENCE
            entity_id=applicant.id,
            document_type="CV",
            file_url=file_url,
            uploaded_by=None  # public user
        ))

        # =========================
        # 4. COMMIT
        # =========================
        db.commit()

        return {
            "message": "Application submitted successfully",
            "applicant_id": applicant.id
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))