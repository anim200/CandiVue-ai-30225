"""Read a CV's text (F1): the file's own text, or OCR when there is none.

Trainer clarification: "CV → is text available? → yes: text extraction /
no: OCR". A PDF with almost no text is treated as a scan: each page is turned
into an image (pypdfium2) and read by Tesseract, locally. A CV that still has
no readable text raises UnreadableCv; screening skips it and goes on.
The screening graph calls the two steps separately (extract_text, then
ocr_extract only when needed); read_cv_text does both in one call.
"""

import io
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pypdfium2
import pytesseract
from docx import Document
from pypdf import PdfReader

MIN_TEXT_CHARS = 80  # less than this: probably a scanned image, not real text
MAX_OCR_PAGES = 5  # a CV is short; this caps OCR time
OCR_SCALE = 300 / 72  # render pages at 300 dpi for good OCR


class UnreadableCv(Exception):
    """No text could be read; the message is safe to show to the interviewer."""


@dataclass
class CvText:
    """The CV's text and whether OCR was needed (shown as "scanned" chip)."""

    text: str
    used_ocr: bool


def read_cv_text(path: Path) -> CvText:
    """Read the text of a saved CV (PDF or DOCX), with OCR for scanned PDFs."""
    text = extract_text(path)
    if has_text(text):
        return CvText(text, used_ocr=False)
    return CvText(ocr_text(path), used_ocr=True)


def has_text(text: str) -> bool:
    """Enough text to work with (else: OCR, or unreadable)."""
    return len(text.strip()) >= MIN_TEXT_CHARS


def extract_text(path: Path) -> str:
    """The file's own text (may be almost empty for a scan)."""
    try:
        data = path.read_bytes()
        if path.suffix == ".docx":
            text = _docx_text(data)
            if not has_text(text):
                raise UnreadableCv("The Word file has no readable text.")
        else:
            text = _pdf_text(data)
    except UnreadableCv:
        raise
    except Exception as exc:  # damaged or password-protected files
        raise UnreadableCv("The file could not be opened. It may be damaged.") from exc
    return _normalise(text)


def ocr_text(path: Path) -> str:
    """Read the page images of a scanned PDF with Tesseract (English)."""
    try:
        text = _ocr_pdf(path.read_bytes())
    except Exception as exc:
        raise UnreadableCv("The scanned file could not be read.") from exc
    if not has_text(text):
        raise UnreadableCv("No readable text was found, even with OCR.")
    return _normalise(text)


def _normalise(text: str) -> str:
    """NFKC turns typographic ligatures ("ﬁ" in "Certiﬁed") and odd spaces
    into plain letters, so headings and words match."""
    return unicodedata.normalize("NFKC", text)


def _pdf_text(data: bytes) -> str:
    """The text layer of every page of a PDF."""
    pages = PdfReader(io.BytesIO(data)).pages
    return "\n".join(page.extract_text() or "" for page in pages)


def _docx_text(data: bytes) -> str:
    """The paragraphs and table cells of a Word document."""
    document = Document(io.BytesIO(data))
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(": ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _ocr_pdf(data: bytes) -> str:
    """Render each page as an image and read it with Tesseract (English)."""
    pdf = pypdfium2.PdfDocument(data)
    try:
        texts = []
        for index in range(min(len(pdf), MAX_OCR_PAGES)):
            image = pdf[index].render(scale=OCR_SCALE).to_pil()
            texts.append(pytesseract.image_to_string(image, lang="eng"))
        return "\n".join(texts)
    finally:
        pdf.close()
