"""Extract text from PDF, TXT and Markdown files.

PDF pages are read with PyMuPDF. Pages with almost no extractable text are
optionally OCR'd with Tesseract. OCR only runs when it is needed, never on
normal digital PDFs.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from app.config import Settings
from app.core.errors import ValidationFailedError
from app.core.logging import get_logger
from app.utils.text import clean_extracted_text, count_tokens

logger = get_logger("extraction")


@dataclass
class ExtractedPage:
    page_number: int
    text: str
    used_ocr: bool = False


@dataclass
class ExtractionResult:
    pages: list[ExtractedPage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return sum(count_tokens(page.text) for page in self.pages)

    @property
    def full_text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text)


def ocr_available() -> bool:
    """True when pytesseract and Pillow are installed (Tesseract binary may still be missing)."""
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


class ExtractionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._ocr_error: str | None = None

    def extract(self, path: Path, file_type: str) -> ExtractionResult:
        if file_type == "pdf":
            return self._extract_pdf(path)
        return self._extract_plain_text(path)

    # -- PDF ----------------------------------------------------------------
    def _extract_pdf(self, path: Path) -> ExtractionResult:
        result = ExtractionResult()
        try:
            document = pymupdf.open(path)
        except Exception as exc:  # corrupted or unsupported PDF
            logger.warning("Could not open PDF %s: %s", path.name, exc)
            raise ValidationFailedError("The PDF could not be opened. It may be corrupted.") from exc

        try:
            if document.needs_pass:
                raise ValidationFailedError("Password-protected PDFs are not supported.")

            for index in range(document.page_count):
                page = document.load_page(index)
                text = clean_extracted_text(page.get_text("text"))

                if len(text) < self.settings.ocr_min_chars_per_page and self.settings.ocr_enabled:
                    ocr_text = self._try_ocr(page)
                    if ocr_text and len(ocr_text) > len(text):
                        text = clean_extracted_text(ocr_text)
                        result.pages.append(ExtractedPage(index + 1, text, used_ocr=True))
                        continue
                    if not ocr_text:
                        result.warnings.append(
                            f"Page {index + 1} has little extractable text and OCR did not run "
                            "(Tesseract not installed or OCR disabled)."
                        )

                result.pages.append(ExtractedPage(index + 1, text))

            if not any(page.text.strip() for page in result.pages):
                raise ValidationFailedError(
                    "No readable text was found in the PDF. It may be a scanned document "
                    "without OCR support."
                )
        finally:
            document.close()

        return result

    def _try_ocr(self, page: pymupdf.Page) -> str | None:
        """OCR one page when the optional dependencies are present."""
        if self._ocr_error:
            return None
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            self._ocr_error = "pytesseract/Pillow are not installed"
            return None

        try:
            pixmap = page.get_pixmap(dpi=200, colorspace=pymupdf.csRGB)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            return pytesseract.image_to_string(image)
        except Exception as exc:  # e.g. the tesseract binary is missing
            self._ocr_error = str(exc)
            logger.warning("OCR failed: %s", exc)
            return None

    # -- TXT / Markdown -----------------------------------------------------
    def _extract_plain_text(self, path: Path) -> ExtractionResult:
        data = path.read_bytes()
        text = self._decode_text(data)
        if not text.strip():
            raise ValidationFailedError("The document contains no readable text.")

        printable_ratio = sum(ch.isprintable() or ch.isspace() for ch in text[:5000]) / max(
            1, len(text[:5000])
        )
        if printable_ratio < 0.85:
            raise ValidationFailedError("The file does not look like a readable text document.")

        cleaned = clean_extracted_text(text)
        return ExtractionResult(pages=[ExtractedPage(page_number=1, text=cleaned)])

    @staticmethod
    def _decode_text(data: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", errors="replace").read()
