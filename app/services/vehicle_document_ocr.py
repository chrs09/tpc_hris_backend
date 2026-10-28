# app/services/vehicle_document_ocr.py
#
# Reads the number off an uploaded vehicle OR (Official Receipt) or CR
# (Certificate of Registration) so the Add/Edit Vehicle Unit form can
# fill it in. Text comes from the PDF itself when it has any, else OCR
# (Tesseract, same setup as the expense receipt OCR). The number is the
# one labelled "OR No." / "CR No." when found, else the first LTO-style
# number (e.g. 0716-25-513493). Only a suggestion -- the form shows it
# for the user to check.

import io
import re

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps

from app.services.expense_ocr_service import ExpenseOCRService

# "OR No.", "O.R. Number", "Official Receipt No:" / "CR No.", "C.R. No." ...
_LABELS = {
    "or": r"(?:O\.?\s?R\.?|OFFICIAL\s+RECEIPT)",
    "cr": r"(?:C\.?\s?R\.?|CERTIFICATE\s+OF\s+REGISTRATION)",
}
_AFTER_LABEL = r"\s*(?:NO\.?|NUMBER|#)\s*[:.#]?\s*([A-Z0-9][A-Z0-9 -]{4,24})"
# LTO-style numbers: 0716-25-513493, 0716-0001234567, or a long digit run.
_NUMBER_PATTERNS = [
    r"\b\d{4}-\d{2}-\d{5,8}\b",
    r"\b\d{4}-\d{6,12}\b",
    r"\b\d{8,15}\b",
]
# Labelled numbers that are something else on the same form.
_OTHER_LABELS = r"(?:MV\s*FILE|ENGINE|CHASSIS|PLATE|TIN|SERIAL|CONTROL|REF)"


def _fix_digits(token: str) -> str:
    """OCR often reads 0 as O and 1 as I / l inside numbers."""
    token = token.strip(" -")
    digits = sum(ch.isdigit() for ch in token)
    if digits >= max(4, len(token.replace("-", "").replace(" ", "")) * 0.6):
        token = token.translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1"}))
    return re.sub(r"\s+", "", token)


def _pdf_text(data: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages[:2])


def _pdf_first_page_image(data: bytes) -> Image.Image:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        return pdf[0].render(scale=2.5).to_pil()
    finally:
        pdf.close()


def _ocr_text(image: Image.Image) -> str:
    path = ExpenseOCRService._resolve_tesseract_path()
    if not path:
        raise RuntimeError("Tesseract OCR is not installed on the server.")
    pytesseract.pytesseract.tesseract_cmd = path

    rgb = ImageOps.exif_transpose(image).convert("RGB")
    gray = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2GRAY)
    gray = ExpenseOCRService._resize_for_ocr(gray)
    gray = ExpenseOCRService._deskew(gray)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    texts = [
        pytesseract.image_to_string(variant, config=config)
        for variant in (gray, otsu)
        for config in ("--psm 6", "--psm 11")
    ]
    return "\n".join(texts)


def read_document_text(data: bytes, content_type: str) -> str:
    if content_type == "application/pdf":
        text = _pdf_text(data)
        if len(text.strip()) >= 20:
            return text
        return _ocr_text(_pdf_first_page_image(data))
    return _ocr_text(Image.open(io.BytesIO(data)))


def find_number(text: str, doc_type: str) -> dict:
    """{"number", "candidates"} from the document's text."""
    upper = text.upper()
    candidates = []

    label = _LABELS[doc_type]
    for match in re.finditer(label + _AFTER_LABEL, upper):
        before = upper[max(0, match.start() - 12):match.start()]
        if re.search(_OTHER_LABELS, before):
            continue
        token = _fix_digits(match.group(1).split("  ")[0])
        if sum(ch.isdigit() for ch in token) >= 5 and token not in candidates:
            candidates.append(token)

    labelled = list(candidates)
    for pattern in _NUMBER_PATTERNS:
        for match in re.finditer(pattern, _fix_digits_in_text(upper)):
            token = match.group(0)
            if token not in candidates:
                candidates.append(token)

    # Drop pieces of a longer candidate ("00000123" of "0716-00000123").
    candidates = [c for c in candidates if not any(c != o and c in o for o in candidates)]
    return {
        "number": (labelled or candidates or [None])[0],
        "candidates": candidates[:5],
    }


def _fix_digits_in_text(text: str) -> str:
    # O / I inside runs of digits ("07I6-25-5I3493" -> "0716-25-513493").
    return re.sub(
        r"[0-9OIl|][0-9OIl|-]{6,}[0-9OIl|]",
        lambda m: m.group(0).translate(str.maketrans({"O": "0", "I": "1", "l": "1", "|": "1"}))
        if sum(ch.isdigit() for ch in m.group(0)) >= 4
        else m.group(0),
        text,
    )


def extract_number(data: bytes, content_type: str, doc_type: str) -> dict:
    text = read_document_text(data, content_type)
    return {**find_number(text, doc_type), "text_found": bool(text.strip())}
