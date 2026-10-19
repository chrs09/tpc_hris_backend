"""Administrator -> Verify Photo: is this an original photo taken through
the system? Upload the image (its SHA-256 must match a stamped photo
exactly) or type the reference code printed on it. A cropped, edited or
re-pasted copy doesn't match; the code then shows what the real photo
was, to compare.
"""

import hashlib

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.photo_seal import PhotoSeal
from app.utils.timezone import utc_to_ph

router = APIRouter(prefix="/photo-verify", tags=["Photo Verify"])

_require_verify = require_role_or_module(
    roles=["superadmin", "admin", "coordinator_admin"],
    module_key="administrator.photo_verification",
)

MAX_BYTES = 25 * 1024 * 1024


def _serialize(seal: PhotoSeal) -> dict:
    return {
        "ref": seal.ref,
        "captured_at": utc_to_ph(seal.captured_at).strftime("%b %d, %Y %I:%M %p") + " PHT",
        "latitude": seal.latitude,
        "longitude": seal.longitude,
        "label": seal.label,
        "file_url": seal.file_url,
    }


@router.post("")
async def verify_photo_file(
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(_require_verify),
):
    data = await photo.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="The file is too large (25 MB max).")
    digest = hashlib.sha256(data).hexdigest()
    seal = db.query(PhotoSeal).filter(PhotoSeal.sha256 == digest).first()
    if not seal:
        return {
            "match": False,
            "message": (
                "Not an original system photo: it doesn't match any photo taken through "
                "Tytan Prime. It may be cropped, edited, a screenshot, or from somewhere "
                "else. If it shows a Ref code, check that code to see the real photo."
            ),
        }
    return {"match": True, "message": "Original photo -- unchanged since it was taken.", **_serialize(seal)}


@router.get("/{ref}")
def verify_photo_ref(
    ref: str,
    db: Session = Depends(get_db),
    _=Depends(_require_verify),
):
    code = ref.strip().upper()
    if not code.startswith("TP-"):
        code = "TP-" + code
    seal = db.query(PhotoSeal).filter(PhotoSeal.ref == code).first()
    if not seal:
        raise HTTPException(status_code=404, detail="No photo has that reference code.")
    return {"match": True, **_serialize(seal)}
