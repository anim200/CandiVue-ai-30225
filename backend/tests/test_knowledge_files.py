"""Upload checks, text extraction and chunking (no database, no AI)."""

import io
import zipfile

import pytest
from docx import Document

from app.knowledge.chunking import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    join_chunks,
    split_into_chunks,
)
from app.knowledge.files import (
    NO_TEXT,
    UNSUPPORTED,
    DocumentError,
    clean_filename,
    detect_file_type,
    extract_text,
)


def make_pdf(text: str) -> bytes:
    """Build a tiny one-page PDF containing the given text."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")  # the header every PDF starts with
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF"
        % (len(objects) + 1, xref)
    )
    return out.getvalue()


def make_docx(text: str) -> bytes:
    """Build a small Word document containing the given text."""
    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_pdf_is_recognised_and_read():
    data = make_pdf("Synthetic company policy text")

    assert detect_file_type(data, "policy.pdf") == "pdf"
    assert "Synthetic company policy text" in extract_text(data, "pdf")


def test_docx_is_recognised_and_read():
    data = make_docx("Remote work is allowed two days a week.")

    assert detect_file_type(data, "policy.docx") == "docx"
    assert "Remote work" in extract_text(data, "docx")


@pytest.mark.parametrize("name, kind", [("notes.txt", "txt"), ("README.md", "md")])
def test_text_files_are_accepted(name, kind):
    assert detect_file_type(b"Plain text", name) == kind


@pytest.mark.parametrize(
    "data, name",
    [
        (b"MZ\x90\x00 fake program", "setup.exe"),
        (b"just text", "renamed.pdf"),  # the name says PDF, the content does not
        (b"PK\x03\x04 not really a zip", "file.docx"),
        (b"\xff\xfe\x00binary", "notes.txt"),  # not UTF-8 text
    ],
)
def test_wrong_file_types_are_refused(data, name):
    with pytest.raises(DocumentError, match=UNSUPPORTED):
        detect_file_type(data, name)


def test_zip_that_is_not_a_word_document_is_refused():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("data.csv", "a,b")

    with pytest.raises(DocumentError, match=UNSUPPORTED):
        detect_file_type(buffer.getvalue(), "data.docx")


def test_document_without_text_is_refused():
    with pytest.raises(DocumentError, match=NO_TEXT):
        extract_text(b"   \n  ", "txt")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\x\\policy.pdf", "policy.pdf"),
        ("bad\x00name\x1f.txt", "badname.txt"),
        ("", "document"),
    ],
)
def test_file_names_are_cleaned(raw, expected):
    assert clean_filename(raw) == expected


def test_short_text_stays_one_passage():
    assert split_into_chunks("One short paragraph.") == ["One short paragraph."]


def test_long_text_is_split_with_overlap():
    paragraphs = [f"Paragraph {n}: " + "word " * 60 for n in range(20)]

    chunks = split_into_chunks("\n\n".join(paragraphs))

    assert len(chunks) > 1
    assert all(len(chunk) <= CHUNK_SIZE + CHUNK_OVERLAP + 2 for chunk in chunks)
    # The start of each passage repeats the end of the previous one.
    assert chunks[0][-CHUNK_OVERLAP:] in chunks[1]


def test_passages_join_back_into_the_document():
    sentences = " ".join(["Some words here."] * 20)
    text = "\n\n".join(f"Paragraph {i}. {sentences}" for i in range(12))

    chunks = split_into_chunks(text)

    assert len(chunks) > 3 and join_chunks(chunks) == text
