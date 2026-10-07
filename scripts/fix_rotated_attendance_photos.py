"""
One-time fix: turn sideways attendance selfies upright.

Selfies uploaded before the iOS rotation fix lost their EXIF "rotate me"
tag, so some are stored sideways. This reads each face's landmarks (eyes above
the mouth = upright) to tell which way is up (see app/services/photo_orientation.py).

Report first (changes nothing):
    python -m scripts.fix_rotated_attendance_photos

Then apply:
    python -m scripts.fix_rotated_attendance_photos --apply

Options:
    --days N        only photos from the last N days (default 60)
    --pending-only  only sides still waiting in Approvals

On --apply each turned photo is saved as a new file and the record
points to it; the original file is left on disk as the backup. Sides
still waiting for review get their face match re-run (score + note
only -- nobody is auto-approved). Photos where no face is found at any
angle (masks, dark photos) are left alone; use the Rotate button in
Approvals for those.
"""

import argparse
import os
from datetime import date, timedelta

import app.models  # noqa: F401  (register every model before querying)
from app.core.database import SessionLocal
from app.models.attendance import AttendanceRecord
from app.models.files import File as FileModel
from app.services.face_recognition_service import FaceRecognitionService
from app.services.photo_orientation import (
    PHOTO_SIDES,
    best_rotation,
    local_path,
    rescore_side,
    rotate_stored_photo,
)

PENDING = ("NEEDS_REVIEW", "FACE_MATCH_FAILED", "NO_PROFILE_PHOTO")


def run(apply: bool, days: int, pending_only: bool):
    db = SessionLocal()
    face_service = FaceRecognitionService()
    side_of = {doc: side for side, doc in PHOTO_SIDES.items()}
    since = date.today() - timedelta(days=days)
    try:
        rows = (
            db.query(FileModel, AttendanceRecord)
            .join(AttendanceRecord, AttendanceRecord.id == FileModel.entity_id)
            .filter(
                FileModel.entity_type == "attendance",
                FileModel.document_type.in_(list(PHOTO_SIDES.values())),
                AttendanceRecord.attendance_date >= since,
            )
            .order_by(AttendanceRecord.attendance_date.desc())
            .all()
        )
        print(f"Checking {len(rows)} photos since {since} ({'APPLY' if apply else 'report only'})\n")
        turned = skipped = missing = 0
        for index, (photo, record) in enumerate(rows, 1):
            side = side_of[photo.document_type]
            if pending_only and getattr(record, f"{side}_face_review_status") not in PENDING:
                continue
            path = local_path(photo.file_url)
            if not os.path.exists(path):
                missing += 1
                continue
            degrees, seen = best_rotation(face_service.app, path)
            if index % 50 == 0:
                print(f"  ... {index}/{len(rows)}")
            if degrees is None:
                skipped += 1
                continue
            turned += 1
            shown = f"face upright at (turn: score) {seen.get('upright_at')}"
            print(
                f"#{record.id} {record.attendance_date} {side}: turn {degrees}° clockwise"
                f"  [{shown}]"
            )
            if apply:
                photo.file_url = rotate_stored_photo(photo.file_url, degrees)
                rescore_side(db, record, side, photo.file_url, face_service)
                db.commit()
                print(
                    f"    -> {getattr(record, f'{side}_face_review_reason')}"
                )
        print(
            f"\n{turned} to turn{' (done)' if apply else ''}, {skipped} already upright"
            f" or no clear face, {missing} files missing on disk."
        )
        if turned and not apply:
            print("Run again with --apply to turn them.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--pending-only", action="store_true")
    args = parser.parse_args()
    run(args.apply, args.days, args.pending_only)
