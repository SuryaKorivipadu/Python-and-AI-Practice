"""Text normalization and chunk-identity hashing.

The core trick that makes incremental reindexing possible: a chunk's ID is derived from (document, position, normalized content) rather than assigned sequentially or derived from the whole document. That means editing one paragraph in a 50-paragraph document changes exactly one chunk_id -- every other paragraph's identity is untouched, so the diff against the stored manifest naturally isolates the change instead of invalidating the document.

Position is part of the identity (not just content) so that two unrelated paragraphs that happen to contain identical text don't collide, and so that inserting a new paragraph is seen as one add rather than shifting every downstream chunk's identity by one slot.
"""

import hashlib
import re
import textwrap

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Collapse whitespace and case so trivial formatting chunk (double spaces, trailing newlines, tab vs. space) doesn't register as a content change."""
    return _WHITESPACE_RE.sub(" ", text.strip().lower())


def content_hash(text: str, position: int, doc_name: str) -> str:
    """Hash normalized content together with its document and position."""
    return hashlib.sha256(
        f"{doc_name}\n{position}\n{normalize_text(text)}".encode("utf-8")
    ).hexdigest()


class Chunk:
    def __init__(
        self,
        doc_name: str,
        position: int,
        text: str,
        content_hash: str,
    ):
        self.doc_name = doc_name
        self.position = position
        self.text = text
        self.content_hash = content_hash


def chunk_document(doc_name: str, text: str, min_chars: int = 1) -> list[Chunk]:
    """Split a document into paragraph-level chunks.

    Paragraphs (blank-line-separated blocks) are the chunk granularity: they are small enough that an edit to one paragraph doesn't force re-embedding unrelated content, and large enough to carry meaningful retrieval context.
    """
    raw_paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[Chunk] = []
    position = 0
    for raw in raw_paragraphs:
        stripped = raw.strip()
        if len(stripped) < min_chars:
            continue
        chunks.append(
            Chunk(
                doc_name=doc_name,
                position=position,
                text=stripped,
                content_hash=content_hash(stripped, position, doc_name),
            )
        )
        position += 1
    return chunks


def print_wrapped_table(
    headers: list[str], rows: list[list[str]], column_widths: list[int]
) -> None:
    def print_row(values: list[str]) -> None:
        wrapped_values = [
            textwrap.wrap(
                value,
                width,
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [""]
            for value, width in zip(values, column_widths)
        ]
        for line_number in range(max(map(len, wrapped_values))):
            cells = [
                lines[line_number] if line_number < len(lines) else ""
                for lines in wrapped_values
            ]
            print(
                "| "
                + " | ".join(
                    cell.ljust(width)
                    for cell, width in zip(cells, column_widths)
                )
                + " |"
            )

    separator = "+" + "+".join("-" * (width + 2) for width in column_widths) + "+"
    print(separator)
    print_row(headers)
    print(separator)
    for row in rows:
        print_row(row)
        print(separator)


###################Test code to demonstrate chunking and hashing behavior. Run this file directly to see the output.###################################################
if __name__ == "__main__":
    doc_name = "test.txt"
    old_data = """
    This document contains only synthetic, AI-generated test text. Every place, object, measurement, and event below is fictional and is included solely to exercise paragraph-based chunking.

    In the imaginary town of Lumenvale, a little blue bell hangs beside the door to the unused map room. It rings gently when a breeze moves through the hallway, although the windows are always closed.

    The made-up weather station recorded 17 silver raindrops on Monday, 23 on Tuesday, and none on Wednesday. These numbers are invented examples, not observations from a real location.
    """
    old_chunks = chunk_document(doc_name, old_data)

    new_data = """
    This document contains only synthetic, AI-generated test text. Every place, object, measurement, and event below is fictional and is included solely to exercise paragraph-based chunking.

    In the imaginary town of Lumenvale, a small blue bell hangs beside the door of the unused map room. It rings softly when a breeze passes through the hallway, even though the windows are always closed.

    The made-up weather station recorded 17 silver raindrops on Monday, 23 on Tuesday, and none on Wednesday. These numbers are invented examples, not observations from a real location.
    """
    new_chunks = chunk_document(doc_name, new_data)

    headers = [
        "Document Name",
        "Position",
        "Old chunk text",
        "Old content hash",
        "New chunk text",
        "New content hash",
    ]
    rows = [
        [
            doc_name,
            str(old_chunk.position),
            old_chunk.text,
            old_chunk.content_hash,
            new_chunk.text,
            new_chunk.content_hash,
        ]
        for old_chunk, new_chunk in zip(old_chunks, new_chunks)
    ]
    print_wrapped_table(headers, rows, [12, 8, 30, 16, 30, 16])

    updated_chunks_by_position = {
        chunk.position: chunk for chunk in new_chunks
    }
    changed_chunks = [
        [
            str(old_chunk.position),
            old_chunk.content_hash,
            old_chunk.text,
            new_chunk.content_hash,
            new_chunk.text,
        ]
        for old_chunk, new_chunk in zip(old_chunks, new_chunks)
        if old_chunk.position == new_chunk.position
        and old_chunk.content_hash != new_chunk.content_hash
    ]

    print("\nChunks with changed content hashes:")
    print_wrapped_table(
        [
            "Position",
            "Old content hash",
            "Old chunk text",
            "New content hash",
            "New chunk text",
        ],
        changed_chunks,
        [8, 16, 30, 16, 30],
    )