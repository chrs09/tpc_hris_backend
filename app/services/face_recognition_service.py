import boto3
import os
from urllib.parse import urlparse, unquote
from datetime import datetime

from app.core.config import settings

AUTO_APPROVE_THRESHOLD = 85.0


class FaceRecognitionService:
    def __init__(self):
        self.client = boto3.client(
            "rekognition",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )

    def _extract_s3_key(self, file_url: str):
        parsed = urlparse(file_url)

        # s3://bucket/key
        if parsed.scheme == "s3":
            return unquote(parsed.path.lstrip("/"))

        # https://bucket.s3.amazonaws.com/key
        return unquote(parsed.path.lstrip("/"))

    def _url_to_local_path(self, file_url: str):
        parsed = urlparse(file_url)

        relative_path = unquote(parsed.path.lstrip("/"))

        return os.path.join(os.getcwd(), relative_path.replace("/", os.sep))

    def _is_s3_url(self, url: str):
        return url.startswith("s3://") or ".amazonaws.com/" in url

    def compare_faces(
        self,
        profile_photo_url: str | None,
        attendance_photo_url: str | None,
    ):
        if not profile_photo_url:
            return {
                "score": None,
                "status": "NO_PROFILE_PHOTO",
                "reason": "Employee has no profile photo.",
                "checked_at": datetime.utcnow(),
            }

        if not attendance_photo_url:
            return {
                "score": None,
                "status": "NO_ATTENDANCE_PHOTO",
                "reason": "Attendance selfie is missing.",
                "checked_at": datetime.utcnow(),
            }

        try:

            print("PROFILE PHOTO URL:", profile_photo_url)
            print("ATTENDANCE PHOTO URL:", attendance_photo_url)

            # --------------------------------------------------
            # S3 MODE
            # --------------------------------------------------
            if self._is_s3_url(profile_photo_url) and self._is_s3_url(
                attendance_photo_url
            ):

                profile_key = self._extract_s3_key(profile_photo_url)
                attendance_key = self._extract_s3_key(attendance_photo_url)

                print("PROFILE KEY:", profile_key)
                print("ATTENDANCE KEY:", attendance_key)

                result = self.client.compare_faces(
                    SourceImage={
                        "S3Object": {
                            "Bucket": settings.AWS_BUCKET_NAME,
                            "Name": profile_key,
                        }
                    },
                    TargetImage={
                        "S3Object": {
                            "Bucket": settings.AWS_BUCKET_NAME,
                            "Name": attendance_key,
                        }
                    },
                    SimilarityThreshold=70,
                )

            # --------------------------------------------------
            # LOCAL MODE
            # --------------------------------------------------
            else:

                profile_path = self._url_to_local_path(profile_photo_url)

                attendance_path = self._url_to_local_path(attendance_photo_url)

                print("PROFILE PATH:", profile_path)
                print("ATTENDANCE PATH:", attendance_path)

                if not os.path.exists(profile_path):
                    raise Exception(f"Profile photo not found: {profile_path}")

                if not os.path.exists(attendance_path):
                    raise Exception(f"Attendance photo not found: {attendance_path}")

                with open(profile_path, "rb") as f:
                    profile_bytes = f.read()

                with open(attendance_path, "rb") as f:
                    attendance_bytes = f.read()

                result = self.client.compare_faces(
                    SourceImage={"Bytes": profile_bytes},
                    TargetImage={"Bytes": attendance_bytes},
                    SimilarityThreshold=70,
                )

            matches = result.get("FaceMatches", [])

            if not matches:
                return {
                    "score": 0,
                    "status": "NEEDS_REVIEW",
                    "reason": "No matching face found.",
                    "checked_at": datetime.utcnow(),
                }

            score = round(matches[0]["Similarity"], 2)

            if score >= AUTO_APPROVE_THRESHOLD:
                return {
                    "score": score,
                    "status": "AUTO_APPROVED",
                    "reason": f"Face matched ({score}%).",
                    "checked_at": datetime.utcnow(),
                }

            return {
                "score": score,
                "status": "NEEDS_REVIEW",
                "reason": (f"Face match score below threshold " f"({score}%)."),
                "checked_at": datetime.utcnow(),
            }

        except Exception as e:
            return {
                "score": None,
                "status": "FACE_MATCH_FAILED",
                "reason": str(e)[:1000],
                "checked_at": datetime.utcnow(),
            }
