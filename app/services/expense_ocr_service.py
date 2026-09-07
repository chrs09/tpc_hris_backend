import base64
import io
import os
import re
import shutil
from collections import defaultdict

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps


class ExpenseOCRService:
    """Extract clean, readable lines from an expense receipt image."""

    MIN_WORD_CONFIDENCE = 30
    MIN_LINE_CONFIDENCE = 35

    @staticmethod
    def _resolve_tesseract_path():
        configured_path = os.environ.get("TESSERACT_CMD")
        if configured_path and os.path.exists(configured_path):
            return configured_path

        path_from_shell = shutil.which("tesseract")
        if path_from_shell:
            return path_from_shell

        windows_candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]

        for candidate in windows_candidates:
            if os.path.exists(candidate):
                return candidate

        return None

    @staticmethod
    def _resize_for_ocr(gray):
        height, width = gray.shape
        largest_dimension = max(width, height)

        if largest_dimension > 2400:
            scale = 2400 / largest_dimension
        elif largest_dimension < 1200:
            scale = min(2, 1200 / largest_dimension)
        else:
            return gray

        return cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

    @staticmethod
    def _deskew(gray):
        """Straighten a photographed receipt so line detection lines up with the true rows of text.

        A receipt photographed even a few degrees off-axis makes Tesseract's own
        row/line segmentation unreliable - a word from one physical line can get
        attached to the line above or below it. Estimating the dominant text
        angle and rotating it out keeps each detected "line" matching an actual
        line printed on the receipt.
        """
        inverted = cv2.bitwise_not(gray)
        _, thresh = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        coords = np.column_stack(np.where(thresh > 0))

        if coords.shape[0] < 20:
            return gray

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        # Ignore near-zero angles (already straight) and outliers (a bad
        # estimate from sparse/noisy text) rather than risk rotating a
        # perfectly good image based on a spurious reading.
        if abs(angle) < 0.5 or abs(angle) > 15:
            return gray

        height, width = gray.shape
        center = (width // 2, height // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(
            gray,
            matrix,
            (width, height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    @staticmethod
    def _generate_ocr_variants(image: Image.Image):
        """Create a small set of useful receipt-specific OCR inputs."""
        rgb = ImageOps.exif_transpose(image).convert("RGB")
        gray = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2GRAY)
        gray = ExpenseOCRService._resize_for_ocr(gray)
        gray = ExpenseOCRService._deskew(gray)
        gray = cv2.fastNlMeansDenoising(
            gray,
            None,
            h=7,
            templateWindowSize=7,
            searchWindowSize=21,
        )

        contrast = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        _, otsu = cv2.threshold(
            contrast,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        )
        adaptive = cv2.adaptiveThreshold(
            contrast,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            9,
        )

        return [gray, otsu, adaptive]

    @staticmethod
    def _clean_line(text: str) -> str:
        text = (text or "").replace("\u00a0", " ")
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"([:;])\s*", r"\1 ", text)
        return text.strip(" |_")

    @staticmethod
    def _is_noise_line(text: str) -> bool:
        if len(text) < 2 or re.fullmatch(r"[\W_]+", text):
            return True

        alphanumeric = len(re.findall(r"[A-Za-z0-9]", text))
        unusual = len(re.findall(r"[^A-Za-z0-9\s.,:/#()&+'%\-]", text))
        compact = re.sub(r"\s+", "", text)

        if alphanumeric < 2:
            return True
        if unusual > max(1, len(compact) * 0.2):
            return True
        return bool(re.fullmatch(r"(.)\1{3,}", compact))

    @staticmethod
    def _ocr_lines_by_row(processed, config: str):
        """Group Tesseract words by their physical receipt row, not by token."""
        data = pytesseract.image_to_data(
            processed,
            config=config,
            output_type=pytesseract.Output.DICT,
        )

        rows = defaultdict(list)
        row_confidences = defaultdict(list)
        row_tops = defaultdict(list)

        for index, word in enumerate(data.get("text", [])):
            word = ExpenseOCRService._clean_line(word)
            if not word:
                continue

            try:
                confidence = float(data["conf"][index])
            except (KeyError, IndexError, TypeError, ValueError):
                continue

            if confidence < ExpenseOCRService.MIN_WORD_CONFIDENCE:
                continue

            key = (
                data.get("block_num", [0])[index],
                data.get("par_num", [0])[index],
                data.get("line_num", [index])[index],
            )
            try:
                left = int(data.get("left", [index])[index])
            except (IndexError, TypeError, ValueError):
                left = index

            try:
                top = int(data.get("top", [index])[index])
            except (IndexError, TypeError, ValueError):
                top = 0

            rows[key].append((left, word))
            row_confidences[key].append(confidence)
            row_tops[key].append(top)

        lines = []
        for key, words_in_row in rows.items():
            words = " ".join(word for _, word in sorted(words_in_row))
            text = ExpenseOCRService._clean_line(words)
            confidence = sum(row_confidences[key]) / len(row_confidences[key])
            # Use the row's actual vertical position on the page rather than
            # Tesseract's block/par/line ids - those ids don't reliably
            # increase top-to-bottom once a receipt is split into multiple
            # text blocks (e.g. a boxed total, a logo, a two-column layout).
            top = min(row_tops[key])

            if (
                confidence >= ExpenseOCRService.MIN_LINE_CONFIDENCE
                and not ExpenseOCRService._is_noise_line(text)
            ):
                lines.append({"text": text, "confidence": round(confidence, 1), "top": top})

        lines.sort(key=lambda line: line["top"])
        return lines

    @staticmethod
    def _score_lines(lines):
        if not lines:
            return -1

        score = 0
        for line in lines:
            text = line["text"]
            words = re.findall(r"[A-Za-z0-9]+", text)
            letters = len(re.findall(r"[A-Za-z]", text))

            score += line["confidence"] / 25
            score += min(len(words), 6)
            if letters >= 3:
                score += 2
            if re.search(r"\b(total|invoice|receipt|date|tin|vat)\b", text, re.I):
                score += 2

        return score

    @staticmethod
    def _dedupe_lines(lines):
        deduped = []
        seen = set()

        for line in lines:
            normalized = re.sub(r"[^a-z0-9]", "", line["text"].lower())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(line)

        return deduped

    @staticmethod
    def _supplier_candidates(lines):
        """Return likely merchant names near the receipt header for user review."""
        blocked = re.compile(
            r"\b(receipt|invoice|official|date|time|tin|vat|tel|phone|"
            r"mobile|address|cashier|transaction|subtotal|total|change|"
            r"payment|qty|quantity|description|unit price|amount|thank)\b",
            re.I,
        )
        labeled = re.compile(
            r"^(?:supplier|vendor|merchant|company|sold\s+by|from)\s*[:#.-]?\s*(.+)$",
            re.I,
        )

        candidates = []
        seen = set()
        for index, line in enumerate(lines[:12]):
            text = line["text"]
            match = labeled.match(text)
            value = ExpenseOCRService._clean_line(match.group(1) if match else text)
            letters = len(re.findall(r"[A-Za-z]", value))
            digits = len(re.findall(r"\d", value))

            if (
                not value
                or value.lower() in seen
                or letters < 3
                or digits > max(2, letters // 2)
                or (blocked.search(value) and not match)
            ):
                continue

            score = 100 if match else 30 - index
            if re.search(r"\b(inc|corp|corporation|ltd|llc|co\.?|trading)\b", value, re.I):
                score += 8
            if value.isupper():
                score += 3

            seen.add(value.lower())
            candidates.append((score, value))

        return [value for _, value in sorted(candidates, reverse=True)[:3]]

    @staticmethod
    def _encode_image(variant) -> str | None:
        """Encode a processed OCR image (numpy array) as a data URI for preview only."""
        if variant is None:
            return None

        success, buffer = cv2.imencode(".png", variant)
        if not success:
            return None

        encoded = base64.b64encode(buffer).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    @staticmethod
    def extract_receipt(file_bytes: bytes) -> dict:
        if not file_bytes:
            return {
                "raw_text": "",
                "lines": [],
                "supplier_candidates": [],
                "enhanced_image": None,
            }

        tesseract_path = ExpenseOCRService._resolve_tesseract_path()
        if not tesseract_path:
            raise RuntimeError(
                "Tesseract OCR is not installed or is not available in PATH. "
                "Please install Tesseract OCR and ensure the 'tesseract' binary is available."
            )

        pytesseract.pytesseract.tesseract_cmd = tesseract_path

        try:
            image = Image.open(io.BytesIO(file_bytes))
            # Pair each attempt's lines with the processed image that produced
            # them, so whichever attempt scores best can also be shown back to
            # the user as a "for reading clarity" preview - this never touches
            # the original file, it only reuses an image already held in memory.
            attempts = []
            for variant in ExpenseOCRService._generate_ocr_variants(image):
                for config in ("--psm 6", "--psm 4", "--psm 11"):
                    lines = ExpenseOCRService._ocr_lines_by_row(variant, config)
                    attempts.append((lines, variant))

            best_lines, best_variant = max(
                attempts,
                key=lambda attempt: ExpenseOCRService._score_lines(attempt[0]),
                default=([], None),
            )
            best_lines = ExpenseOCRService._dedupe_lines(best_lines)
            text_lines = [line["text"] for line in best_lines]

            return {
                "raw_text": "\n".join(text_lines),
                "lines": text_lines,
                "supplier_candidates": ExpenseOCRService._supplier_candidates(best_lines),
                "enhanced_image": ExpenseOCRService._encode_image(best_variant),
            }
        except Exception as exc:
            raise RuntimeError(f"Failed to process receipt image: {exc}") from exc

    @staticmethod
    def extract_text(file_bytes: bytes) -> str:
        """Compatibility wrapper for consumers that only need receipt text."""
        return ExpenseOCRService.extract_receipt(file_bytes)["raw_text"]
