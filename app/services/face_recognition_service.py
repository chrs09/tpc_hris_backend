import os
from datetime import datetime
from urllib.parse import unquote, urlparse

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from app.core.config import settings


# TEMPORARY threshold.
# Tune this after testing multiple employees/selfies.
AUTO_APPROVE_THRESHOLD = 0.50


class FaceRecognitionService:

    def __init__(self):
        """
        Initialize InsightFace once.

        Uses CPU because the office server does not have
        a dedicated NVIDIA GPU.
        """
        self.app = FaceAnalysis(
            name="buffalo_l",
            providers=["CPUExecutionProvider"],
        )

        self.app.prepare(
            ctx_id=0,
            det_size=(640, 640),
        )

    # ==========================================================
    # URL -> LOCAL FILE PATH
    # ==========================================================

    def _url_to_local_path(self, file_url: str) -> str:
        """
        Convert a stored API URL such as:

        https://api.tytanprime.net/uploads/employees/106/photo.jpg

        into the actual local server path:

        C:/.../tpc_hris_backend/uploads/employees/106/photo.jpg
        """

        parsed = urlparse(file_url)

        # Extract path:
        # /uploads/employees/106/photo.jpg
        relative_path = unquote(
            parsed.path.lstrip("/")
        )

        # Remove the public /uploads prefix.
        if relative_path.startswith("uploads/"):
            relative_path = relative_path[len("uploads/"):]

        return os.path.join(
            settings.UPLOAD_FOLDER,
            relative_path.replace("/", os.sep),
        )

    # ==========================================================
    # IMAGE LOADING
    # ==========================================================

    def _load_image(self, file_path: str, label: str):
        """
        Load an image from the local uploads directory.
        """

        if not os.path.exists(file_path):
            raise Exception(
                f"{label} photo not found: {file_path}"
            )

        image = cv2.imread(file_path)

        if image is None:
            raise Exception(
                f"Could not read {label} photo: {file_path}"
            )

        return image

    # ==========================================================
    # FACE DETECTION
    # ==========================================================

    def _get_face(self, image, label: str):
        """
        Detect faces in an image.

        For attendance verification we expect exactly one face.
        """

        faces = self.app.get(image)

        if len(faces) == 0:
            raise Exception(
                f"No face detected in {label} photo."
            )

        if len(faces) > 1:
            raise Exception(
                f"Multiple faces detected in {label} photo."
            )

        return faces[0]

    # ==========================================================
    # FACE COMPARISON
    # ==========================================================

    def compare_faces(
        self,
        profile_photo_url: str | None,
        attendance_photo_url: str | None,
    ):
        """
        Compare an employee's profile photo against
        their attendance selfie.

        Returns the same result structure previously used
        by the attendance endpoint.
        """

        # ------------------------------------------------------
        # PROFILE PHOTO CHECK
        # ------------------------------------------------------

        if not profile_photo_url:
            return {
                "score": None,
                "status": "NO_PROFILE_PHOTO",
                "reason": "Employee has no profile photo.",
                "checked_at": datetime.utcnow(),
            }

        # ------------------------------------------------------
        # ATTENDANCE PHOTO CHECK
        # ------------------------------------------------------

        if not attendance_photo_url:
            return {
                "score": None,
                "status": "NO_ATTENDANCE_PHOTO",
                "reason": "Attendance selfie is missing.",
                "checked_at": datetime.utcnow(),
            }

        try:

            print("========================================")
            print("FACE RECOGNITION")
            print("========================================")

            print(
                "PROFILE PHOTO URL:",
                profile_photo_url,
            )

            print(
                "ATTENDANCE PHOTO URL:",
                attendance_photo_url,
            )

            # --------------------------------------------------
            # CONVERT URLS TO LOCAL FILE PATHS
            # --------------------------------------------------

            profile_path = self._url_to_local_path(
                profile_photo_url
            )

            attendance_path = self._url_to_local_path(
                attendance_photo_url
            )

            print(
                "PROFILE PHOTO PATH:",
                profile_path,
            )

            print(
                "ATTENDANCE PHOTO PATH:",
                attendance_path,
            )

            # --------------------------------------------------
            # LOAD IMAGES
            # --------------------------------------------------

            profile_image = self._load_image(
                profile_path,
                "Profile",
            )

            attendance_image = self._load_image(
                attendance_path,
                "Attendance",
            )

            # --------------------------------------------------
            # DETECT FACES
            # --------------------------------------------------

            profile_face = self._get_face(
                profile_image,
                "profile",
            )

            attendance_face = self._get_face(
                attendance_image,
                "attendance",
            )

            # --------------------------------------------------
            # GET NORMALIZED EMBEDDINGS
            # --------------------------------------------------

            profile_embedding = (
                profile_face.normed_embedding
            )

            attendance_embedding = (
                attendance_face.normed_embedding
            )

            # --------------------------------------------------
            # COSINE SIMILARITY
            # --------------------------------------------------

            similarity = float(
                np.dot(
                    profile_embedding,
                    attendance_embedding,
                )
            )

            score = round(similarity, 4)

            print(
                "FACE SIMILARITY:",
                score,
            )

            print(
                "FACE THRESHOLD:",
                AUTO_APPROVE_THRESHOLD,
            )

            # --------------------------------------------------
            # MATCH
            # --------------------------------------------------

            if similarity >= AUTO_APPROVE_THRESHOLD:

                print(
                    "FACE RESULT: AUTO_APPROVED"
                )

                return {
                    "score": score,
                    "status": "AUTO_APPROVED",
                    "reason": (
                        f"Face matched "
                        f"(similarity: {score})."
                    ),
                    "checked_at": datetime.utcnow(),
                }

            # --------------------------------------------------
            # NO MATCH
            # --------------------------------------------------

            print(
                "FACE RESULT: NEEDS_REVIEW"
            )

            return {
                "score": score,
                "status": "NEEDS_REVIEW",
                "reason": (
                    f"Face similarity below "
                    f"threshold ({score})."
                ),
                "checked_at": datetime.utcnow(),
            }

        # ------------------------------------------------------
        # FACE RECOGNITION ERROR
        # ------------------------------------------------------

        except Exception as e:

            print(
                "FACE RECOGNITION ERROR:",
                str(e),
            )

            return {
                "score": None,
                "status": "FACE_MATCH_FAILED",
                "reason": str(e)[:1000],
                "checked_at": datetime.utcnow(),
            }