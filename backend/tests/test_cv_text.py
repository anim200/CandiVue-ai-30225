"""Reading a CV's text (F1): OCR for a scanned PDF (the real Tesseract in the
backend image) and a clear error when nothing is readable."""

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.screening.text import UnreadableCv, read_cv_text

A4 = (1240, 1754)  # pixels at 150 dpi


def scanned_pdf(path, lines: list[str]) -> None:
    """An image-only PDF (no text layer), like a scanned CV."""
    image = Image.new("RGB", A4, "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=40)
    for number, line in enumerate(lines):
        draw.text((80, 100 + number * 70), line, fill="black", font=font)
    image.save(path, "PDF", resolution=150)


def test_a_scanned_cv_is_read_with_ocr(tmp_path):
    path = tmp_path / "scan.pdf"
    scanned_pdf(
        path,
        [
            "Jordan Sample",
            "PHP developer: Laravel and Docker",
            "Work Experience 2019 to 2026",
            "Builds REST APIs and ships them in containers",
        ],
    )

    result = read_cv_text(path)

    assert result.used_ocr is True  # shown with the "scanned" chip
    assert "Laravel" in result.text and "Docker" in result.text


def test_a_blank_scan_is_unreadable_with_a_clear_reason(tmp_path):
    path = tmp_path / "blank.pdf"
    Image.new("RGB", A4, "white").save(path, "PDF", resolution=150)

    with pytest.raises(UnreadableCv, match="No readable text"):
        read_cv_text(path)
