import io

import cv2
import numpy as np
import pytesseract
from PIL import Image


class ExpenseOCRService:
    """
    Handles OCR processing for finance expense receipt images.

    This service does not create or update database records.
    It only extracts text from an uploaded image.
    """

    @staticmethod
    def extract_text(file_bytes: bytes) -> str:
        if not file_bytes:
            return ""

        try:
            # Load image from uploaded bytes
            image = Image.open(
                io.BytesIO(file_bytes)
            ).convert("RGB")

            # Convert PIL image to NumPy array
            image_array = np.array(image)

            # Convert RGB to grayscale
            gray = cv2.cvtColor(
                image_array,
                cv2.COLOR_RGB2GRAY,
            )

            # Enlarge image for better OCR accuracy
            gray = cv2.resize(
                gray,
                None,
                fx=2,
                fy=2,
                interpolation=cv2.INTER_CUBIC,
            )

            # Reduce small image noise
            gray = cv2.GaussianBlur(
                gray,
                (3, 3),
                0,
            )

            # Convert to black and white
            _, threshold = cv2.threshold(
                gray,
                0,
                255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU,
            )

            # Run OCR
            text = pytesseract.image_to_string(
                threshold,
                config="--psm 6",
            )

            return text.strip()

        except Exception as exc:
            raise RuntimeError(
                f"Failed to process receipt image: {exc}"
            ) from exc