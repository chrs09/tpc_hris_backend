"""Turning stored attendance selfies upright.

Selfies saved before the iOS fix in file_service._watermark_timestamp
lost their EXIF "rotate me" tag, so some are stored sideways. These
helpers rotate a stored photo (by hand from Approvals, or by face
detection in scripts/fix_rotated_attendance_photos.py).

A rotated photo is saved as a NEW file and the File row points to it:
the original stays on disk as the backup, and browsers can't keep
showing a cached sideways copy under the same URL.
"""

import os
import uuid
from datetime import datetime
from urllib.parse import unquote, urlparse

from PIL import Image

from app.core.config import settings

PHOTO_SIDES = {"time_in": "ATTENDANCE_TIME_IN", "time_out": "ATTENDANCE_TIME_OUT"}

# A face must be detected at least this confidently for the auto-fix to
# trust its landmarks.
MIN_DETECTION = 0.6


def local_path(file_url: str) -> str:
    """/uploads/... URL -> file on this server's disk."""
    relative = unquote(urlparse(file_url).path.lstrip("/"))
    if relative.startswith("uploads/"):
        relative = relative[len("uploads/"):]
    return os.path.join(settings.UPLOAD_FOLDER, relative.replace("/", os.sep))


def rotate_stored_photo(file_url: str, degrees: int) -> str:
    """Saves the photo turned `degrees` clockwise as a new file next to
    the original; returns the new URL."""
    if settings.FILE_STORAGE not in ("local", "", None):
        raise ValueError("Rotating photos works only with local file storage.")
    if degrees % 90 or degrees % 360 == 0:
        raise ValueError("Rotate by 90, 180 or 270 degrees.")
    path = local_path(file_url)
    if not os.path.exists(path):
        raise FileNotFoundError("Photo file not found on the server.")

    with Image.open(path) as image:
        rotated = image.rotate(-(degrees % 360), expand=True)
        if rotated.mode not in ("RGB", "L"):
            rotated = rotated.convert("RGB")
        extension = os.path.splitext(path)[1].lower() or ".jpg"
        new_name = f"{uuid.uuid4()}{extension}"
        new_path = os.path.join(os.path.dirname(path), new_name)
        save_kwargs = {"quality": 92} if extension in (".jpg", ".jpeg") else {}
        rotated.save(new_path, **save_kwargs)

    base, _, _ = file_url.rpartition("/")
    return f"{base}/{new_name}"


def rescore_side(db, record, side: str, photo_url: str, face_service=None) -> None:
    """Re-runs the face match on the turned photo. Only updates the
    score and the note -- a pending side still waits for its approver."""
    from app.models.files import File as FileModel
    from app.services.face_recognition_service import FaceRecognitionService

    status = getattr(record, f"{side}_face_review_status")
    if status not in ("NEEDS_REVIEW", "FACE_MATCH_FAILED"):
        return
    profile = (
        db.query(FileModel)
        .filter(
            FileModel.entity_type == "employee",
            FileModel.entity_id == record.employee_id,
            FileModel.document_type == "PROFILE_IMAGE",
        )
        .first()
    )
    if not profile:
        return
    face_service = face_service or FaceRecognitionService()
    result = face_service.compare_faces(profile.file_url, photo_url)
    old = getattr(record, f"{side}_face_match_score")
    if result["score"] is None:
        note = f"Photo rotated; {result['reason']}"
    else:
        passes = " -- now above the match threshold" if result["status"] == "AUTO_APPROVED" else ""
        was = f" (was {old})" if old is not None else ""
        note = f"Photo rotated upright; face similarity {result['score']}{was}{passes}."
        setattr(record, f"{side}_face_match_score", result["score"])
        if status == "FACE_MATCH_FAILED":
            # A face is now found: it's a normal similarity review.
            setattr(record, f"{side}_face_review_status", "NEEDS_REVIEW")
    setattr(record, f"{side}_face_review_reason", note[:1000])
    setattr(record, f"{side}_face_checked_at", datetime.utcnow())


def _face_direction(face_app, image):
    """Angle (degrees, image coords, y down) from the eyes to the mouth
    of the clearest face -- about 90 when the face is upright -- and
    its detection score. The detector finds sideways faces just as
    confidently, so the landmarks, not the score, tell which way is up."""
    import math

    faces = [f for f in face_app.get(image) if float(f.det_score) >= MIN_DETECTION]
    if not faces:
        return None, 0.0
    face = max(faces, key=lambda f: float(f.det_score))
    eyes, mouth = face.kps[:2].mean(axis=0), face.kps[3:5].mean(axis=0)
    dx, dy = mouth - eyes
    return math.degrees(math.atan2(dy, dx)), float(face.det_score)


def best_rotation(face_app, path: str):
    """Clockwise degrees (90/180/270) that turn the photo upright, or
    None when it already is or no clear face is found. Also returns
    what was seen (angle, score) for the report."""
    import cv2

    image = cv2.imread(path)
    if image is None:
        return None, {}
    # Try all four turns; a turn counts when the face reads upright
    # there (eyes->mouth pointing down, within 25°). Of those, the one
    # detected most clearly wins.
    turns = {
        0: image,
        90: cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE),
        180: cv2.rotate(image, cv2.ROTATE_180),
        270: cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE),
    }
    upright = {}
    for degrees, turned in turns.items():
        angle, score = _face_direction(face_app, turned)
        if angle is not None and abs(angle - 90) <= 25:
            upright[degrees] = round(score, 2)
    seen = {"upright_at": upright}
    if not upright:
        return None, seen  # no clear face at any angle
    best = max(upright, key=upright.get)
    if best == 0:
        return None, seen
    if 0 in upright and upright[best] - upright[0] < 0.05:
        return None, seen  # too close to call -- leave it
    return best, seen
