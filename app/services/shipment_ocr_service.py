import io
import re

import pytesseract
from PIL import Image
from rapidfuzz import fuzz

from app.services.expense_ocr_service import ExpenseOCRService

# Reuse the exact preprocessing pipeline built for expense receipts --
# deskew/denoise/multi-variant/multi-PSM is generic to "clean OCR off a
# phone photo of a printed document", not specific to receipts.
_resolve_tesseract_path = ExpenseOCRService._resolve_tesseract_path
_generate_ocr_variants = ExpenseOCRService._generate_ocr_variants
_ocr_lines_by_row = ExpenseOCRService._ocr_lines_by_row
_dedupe_lines = ExpenseOCRService._dedupe_lines
_score_lines = ExpenseOCRService._score_lines
_clean_line = ExpenseOCRService._clean_line


class ShipmentOCRService:
    """Extracts a candidate shipment number and destination store name
    from a photographed Invoice or LM (loading manifest). Never returns a
    single forced answer -- always a ranked list of candidates with a
    confidence, so the mobile Checkout step can pre-fill a field while
    still letting the driver correct a bad read before submitting."""

    _SHIPMENT_LABEL_RE = re.compile(
        r"^(?:shipment|manifest|dr|invoice|s\.?o\.?)\s*(?:no\.?|#)?\s*[:#-]?\s*(.+)$",
        re.I,
    )
    # Alphanumeric code, at least one digit, 6-20 chars (dashes allowed).
    _CODE_RE = re.compile(r"(?=[A-Z0-9-]{6,20}\b)(?=[A-Z0-9-]*\d)[A-Z0-9-]+")

    @staticmethod
    def _ocr_lines(file_bytes: bytes) -> list[dict]:
        if not file_bytes:
            return []

        tesseract_path = _resolve_tesseract_path()
        if not tesseract_path:
            raise RuntimeError(
                "Tesseract OCR is not installed or is not available in PATH."
            )
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

        image = Image.open(io.BytesIO(file_bytes))

        attempts = []
        for variant in _generate_ocr_variants(image):
            for config in ("--psm 6", "--psm 4", "--psm 11"):
                lines = _ocr_lines_by_row(variant, config)
                attempts.append(lines)

        best_lines = max(attempts, key=_score_lines, default=[])
        return _dedupe_lines(best_lines)

    @staticmethod
    def extract_shipment_number(lines: list[dict]) -> list[dict]:
        """Ranked candidates: [{"value": str, "confidence": float}, ...],
        highest confidence first. Prefers lines with a recognizable label
        (Shipment No./Manifest/DR#/Invoice#) over a bare code match."""
        candidates: list[tuple[float, str]] = []
        seen = set()

        for line in lines:
            text = line["text"]

            labeled = ShipmentOCRService._SHIPMENT_LABEL_RE.match(text)
            search_text = labeled.group(1) if labeled else text

            for match in ShipmentOCRService._CODE_RE.finditer(search_text.upper()):
                code = match.group(0).strip("-")
                if len(code) < 6 or code in seen:
                    continue
                seen.add(code)

                score = line["confidence"] / 100
                if labeled:
                    score += 1.0
                candidates.append((score, code))

        candidates.sort(reverse=True, key=lambda c: c[0])
        return [
            {"value": value, "confidence": round(min(score, 1.0) * 100, 1)}
            for score, value in candidates[:5]
        ]

    @staticmethod
    def match_store_name(lines: list[dict], candidate_stores: list) -> list[dict]:
        """Fuzzy-matches OCR'd text lines against `candidate_stores` (Store
        model instances). Returns ranked [{"store_id", "name", "confidence"}]
        -- highest similarity first, deduped by store."""
        best_by_store: dict[int, float] = {}

        for line in lines:
            text = _clean_line(line["text"])
            if len(text) < 3:
                continue

            for store in candidate_stores:
                similarity = fuzz.partial_ratio(text.lower(), store.name.lower())
                if similarity < 60:
                    continue
                if similarity > best_by_store.get(store.id, 0):
                    best_by_store[store.id] = similarity

        store_by_id = {store.id: store for store in candidate_stores}
        ranked = sorted(best_by_store.items(), key=lambda item: item[1], reverse=True)

        return [
            {
                "store_id": store_id,
                "name": store_by_id[store_id].name,
                "confidence": round(similarity, 1),
            }
            for store_id, similarity in ranked[:5]
        ]

    @staticmethod
    def extract_checkout_fields(
        invoice_bytes: bytes, lm_bytes: bytes, candidate_stores: list
    ) -> dict:
        """Runs OCR on both the Invoice and LM photos and merges candidates
        from both -- a shipment number or store name found on either
        document counts. Any single-image OCR failure degrades to empty
        candidates for that image rather than failing the whole Checkout
        step (the driver can always type the shipment number / pick the
        store manually)."""
        lines: list[dict] = []
        for file_bytes in (invoice_bytes, lm_bytes):
            try:
                lines.extend(ShipmentOCRService._ocr_lines(file_bytes))
            except Exception:
                continue

        return {
            "shipment_number_candidates": ShipmentOCRService.extract_shipment_number(lines),
            "store_candidates": ShipmentOCRService.match_store_name(lines, candidate_stores),
        }
