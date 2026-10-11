"""Cuts a document's text into passages ("chunks") for the knowledge base.

Search compares a question with each passage, so passages should be small
enough to be about one topic but big enough to make sense alone. Passages
overlap a little, so a sentence cut at the border is still found.
"""

import re

CHUNK_SIZE = 1000  # characters per passage (about 150-200 words)
CHUNK_OVERLAP = 150  # characters repeated from the end of the previous passage


def split_into_chunks(text: str) -> list[str]:
    """Split text into overlapping passages, preferring paragraph borders."""
    # Tidy the text: no trailing spaces, at most one empty line in a row.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        # A very long paragraph is cut into pieces of CHUNK_SIZE first.
        pieces = [
            paragraph[i : i + CHUNK_SIZE] for i in range(0, len(paragraph), CHUNK_SIZE)
        ]
        for piece in pieces:
            if current and len(current) + len(piece) + 2 > CHUNK_SIZE:
                chunks.append(current)
                current = current[-CHUNK_OVERLAP:] + "\n\n" + piece  # overlap
            else:
                current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks
